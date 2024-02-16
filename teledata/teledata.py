import numpy as np

from netqasm.sdk.classical_communication.socket import Socket
from netqasm.sdk.connection import BaseNetQASMConnection
from netqasm.sdk.classical_communication.message import StructuredMessage
from netqasm.sdk.toolbox.state_prep import set_qubit_state
from netqasm.sdk.epr_socket import EPRSocket
from netqasm.sdk.qubit import Qubit

from squidasm.sim.stack.program import Program, ProgramContext, ProgramMeta
from squidasm.util import create_two_node_network, get_qubit_state, get_reference_state
from squidasm.run.stack.config import StackNetworkConfig
from squidasm.run.stack.run import run


class AliceProgram(Program):
    PEER_NAME = "Bob"

    @property
    def meta(self) -> ProgramMeta:
        return ProgramMeta(
            name="tutorial_program",
            csockets=[self.PEER_NAME],
            epr_sockets=[self.PEER_NAME],
            max_qubits=2,
        )

    def run(self, context: ProgramContext):
        socket = context.csockets[self.PEER_NAME]
        epr_socket = context.epr_sockets[self.PEER_NAME]
        connection = context.connection

        phi, theta = np.random.random()*3.1415, np.random.random()*3.141
        # phi, theta = 0, 0
        out1 = get_reference_state(phi, theta)

        q0 = Qubit(connection)
        set_qubit_state(q0, phi, theta)
        epr1 = epr_socket.create_keep()[0]
        yield from connection.flush()

        q0.cnot(epr1)
        q0.H()

        r0 = q0.measure()
        r1 = epr1.measure()
        yield from connection.flush()

        msg = f"{int(r0)},{int(r1)}"
        socket.send_structured(StructuredMessage("Measurement", msg))

        return out1


class BobProgram(Program):
    PEER_NAME = "Alice"

    @property
    def meta(self) -> ProgramMeta:
        return ProgramMeta(
            name="tutorial_program",
            csockets=[self.PEER_NAME],
            epr_sockets=[self.PEER_NAME],
            max_qubits=1,
        )

    def run(self, context: ProgramContext):
        socket = context.csockets[self.PEER_NAME]
        epr_socket = context.epr_sockets[self.PEER_NAME]
        connection = context.connection

        epr2 = epr_socket.recv_keep()[0]
        yield from connection.flush()


        msg = yield from socket.recv_structured()
        assert isinstance(msg, StructuredMessage)

        r0, r1 = msg.payload.split(",")

        if int(r1):
            epr2.X()
        if int(r0):
            epr2.Z()

        yield from connection.flush()

        return get_qubit_state(epr2, "Bob")


if __name__ == "__main__":
    # import network configuration from file
    cfg = StackNetworkConfig.from_file("config.yaml")

    # Create instances of programs to run
    alice_program = AliceProgram()
    bob_program = BobProgram()

    # Run the simulation. Programs argument is a mapping of network node labels to programs to run on that node
    out_a, out_b = run(
        config=cfg,
        programs={"Alice": alice_program, "Bob": bob_program},
        num_times=1
        )

    print(f"{out_a} \n{out_b}")
