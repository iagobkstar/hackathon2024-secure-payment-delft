from abc import abstractmethod
from typing import List

from netqasm.sdk.connection import BaseNetQASMConnection
from netqasm.sdk.qubit import Qubit
from squidasm.util.util import get_qubit_state

from squidasm.sim.stack.program import Program, ProgramContext, ProgramMeta


class AbstractNode(Program):
    """ Abstract class that includes a register of qubits and peers the node is connected to

    Parameters:
    - name: str -> The name of the node
    - peers: List[str] -> The nodes that are connected to this node
    - qubits: int -> The maximum number of qubits that this node can hold
    """
    def __init__(self, *args, name: str, peers: List[str], qubits: int = 1, **kwargs):
        super().__init__(*args, **kwargs)
        self._name = name
        self._peers = peers
        self._qubits = [None for i in range(qubits)]
        self._max_qubits = qubits
        self._log = ""

    @property
    def meta(self) -> ProgramMeta:
        return ProgramMeta(
            name=self._name,
            csockets=self.peers,
            epr_sockets=self.peers,
            max_qubits=self._max_qubits,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def peers(self) -> List[str]:
        return self._peers

    @property
    def max_qubits(self) -> int:
        return self._max_qubits

    @property
    def qubits(self) -> List[Qubit]:
        return self._qubits

    @abstractmethod
    def run(self, context: ProgramContext):
        raise NotImplementedError(str(self.__class__) + " must be extended to run program")

    def get_qubit_state(self, index, *args, **kwargs):
        """ Retrieves the underlying quantum state of qubit index in density matrix formalism.
        """
        if not isinstance(index, int):
            raise TypeError(f"index {index} not int")
        return get_qubit_state(self.qubits[index], self.name, **kwargs)

    def generate_epr_send(
        self, 
        target_peer: str,
        context: ProgramContext,
        connection: BaseNetQASMConnection
    ):
        """ Wrapper for epr_socket.create_keep()
        """

        if not target_peer in self.peers:
            raise Exception(f"{target_peer} not in {self.peers}")

        epr_socket = context.epr_sockets[target_peer]

        qubit = epr_socket.create_keep()[0]
        yield from connection.flush()

        return qubit

    def generate_epr_recv(
        self, 
        source_peer: str,
        context: ProgramContext,
        connection: BaseNetQASMConnection
    ):
        """ Wrapper for epr_socket.recv_keep()
        """

        if not source_peer in self.peers:
            raise Exception(f"{source_peer} not in {self.peers}")

        epr_socket = context.epr_sockets[source_peer]

        qubit = epr_socket.recv_keep()[0]
        yield from connection.flush()

        return qubit

    def distributed_cnot_source(
        self,
        source_qubit: Qubit,
        target_peer: str,
        context: ProgramContext,
        connection: BaseNetQASMConnection
    ):
        """ Perform a distributed CNOT gate as source

        Parameters:
        - source_qubit: Qubit -> The qubit that is used as control source from local node
        - target_peer: str -> The connected node that will receive the control. The qubit it will
                              be applied upon will be decided by the target peer
        """

        if not target_peer in self.peers:
            raise Exception(f"{target_peer} not in {self.peers}")

        csocket = context.csockets[target_peer]
        epr_socket = context.epr_sockets[target_peer]

        # Check if there are available communication qubits and get its index
        available = [q is not None for q in self.qubits].count(True)
        if not available > 0:
            raise Exception("No communication qubits available")

        # Send request to generate EPR pair in communication qubit
        comm_qubit = epr_socket.create_keep()[0]

        # ___________________ REMOTE CNOT PROTOCOL ___________________
        source_qubit.cnot(comm_qubit)
        local_meas = comm_qubit.measure()
        yield from connection.flush()

        # Send result of local measurement
        csocket.send(f"{int(local_meas)}")
        yield from connection.flush()

        # Receive result of remote measurement and apply Z gate if True
        rem_meas = yield from csocket.recv()
        if int(rem_meas):
            source_qubit.Z()
        yield from connection.flush()

        # Free up communication qubit
        comm_qubit = None
        return source_qubit

    def distributed_cnot_target(
        self,
        target_qubit: Qubit,
        source_peer: str,
        context: ProgramContext,
        connection: BaseNetQASMConnection
    ):
        """ Perform a distributed CNOT gate as target

        Parameters:
        - target_qubit: Qubit -> The qubit upon which the control will be performed from local node
        - target_peer: str -> The connected node that will be the source of control
        """

        if not source_peer in self.peers:
            raise Exception(f"{source_peer} not in {self.peers}")

        csocket = context.csockets[source_peer]
        epr_socket = context.epr_sockets[source_peer]

        # Check if there are available communication qubits and get its index
        available = [q is not None for q in self.qubits].count(True)
        if not available > 0 :
            raise Exception("No communication qubits available")

        # Accept request to generate EPR pair in communication qubit  
        comm_qubit = epr_socket.recv_keep()[0]

        # ___________________ REMOTE CNOT PROTOCOL ___________________
        comm_qubit.cnot(target_qubit)
        comm_qubit.H()
        local_meas = comm_qubit.measure()
        yield from connection.flush()
    
        # Receive result of remote measurement and apply X gate if True
        rem_meas = yield from csocket.recv()
        if int(rem_meas):
            target_qubit.X()
        yield from connection.flush()

        csocket.send(f"{int(local_meas)}")
        yield from connection.flush()

        # Free up communication qubit
        comm_qubit = None
        return target_qubit

    def teleport_data_send(
        self,
        source_qubit: Qubit,
        target_peer: str,
        context: ProgramContext,
        connection: BaseNetQASMConnection
    ):
        """ Perform a teledata operation (teleport the state of a qubit)

        Parameters:
        - source_qubit: Qubit -> The qubit that is used as control source from local node
        - target_peer: str -> The connected node that will receive the teleported qubit
        """

        if not target_peer in self.peers:
            raise Exception(f"{target_peer} not in {self.peers}")

        csocket = context.csockets[target_peer]
        epr_socket = context.epr_sockets[target_peer]

        comm_qubit = epr_socket.create_keep()[0]
        yield from connection.flush()

        source_qubit.cnot(comm_qubit)
        source_qubit.H()

        r0 = source_qubit.measure()
        r1 = comm_qubit.measure()
        yield from connection.flush()

        msg = f"{int(r0)},{int(r1)}"
        csocket.send(msg)

        source_qubit = None
        comm_qubit = None
        return source_qubit

    def teleport_data_recv(
        self,
        source_peer: str,
        context: ProgramContext,
        connection: BaseNetQASMConnection
    ):
        """ Perform a teledata operation (teleport the state of a qubit)

        Parameters:
        - source_peer: str -> The connected node that will send the teleported qubit

        Returns:
        - qubit: Qubit
        """

        if not source_peer in self.peers:
            raise Exception(f"{source_peer} not in {self.peers}")

        csocket = context.csockets[source_peer]
        epr_socket = context.epr_sockets[source_peer]

        comm_qubit = epr_socket.recv_keep()[0]
        yield from connection.flush()

        msg = yield from csocket.recv()
        r0, r1 = msg.split(",")

        if int(r1):
            comm_qubit.X()
        if int(r0):
            comm_qubit.Z()

        yield from connection.flush()

        return comm_qubit
