from netqasm.sdk.classical_communication.socket import Socket
from netqasm.sdk.connection import BaseNetQASMConnection
from netqasm.sdk.epr_socket import EPRSocket
from netqasm.sdk.qubit import Qubit

from netsquid_magic.models.perfect import PerfectLinkConfig
from netsquid_netbuilder.modules.clinks.default import DefaultCLinkConfig
from netsquid_netbuilder.util.network_generation import create_complete_graph_network

from squidasm.run.stack.run import run
from squidasm.sim.stack.program import ProgramContext

from AbstractNode import AbstractNode


class Alice(AbstractNode):
    def __init__(self,  *args, apply_H=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_H = apply_H

    def run(self, context: ProgramContext):
        connection = context.connection

        self.qubits[0] = yield from self.generate_epr_send(
            "Bob", context, connection
            )
        self.qubits[0] = yield from self.distributed_cnot_source(
            self.qubits[0], "Charlie", context, connection
            )

        if self.apply_H:
            self.qubits[0].H()

        result = self.qubits[0].measure()
        yield from connection.flush()

        return int(result)


class Bob(AbstractNode):
    def __init__(self,  *args, apply_H=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_H = apply_H

    def run(self, context: ProgramContext):
        connection = context.connection

        self.qubits[0] = yield from self.generate_epr_recv(
            "Alice", context, connection
            )

        if self.apply_H:
            self.qubits[0].H()

        result = self.qubits[0].measure()
        yield from connection.flush()

        return int(result)


class Charlie(AbstractNode):
    def __init__(self,  *args, apply_H=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_H = apply_H

    def run(self, context: ProgramContext):
        connection = context.connection

        self.qubits[0] = Qubit(connection)
        yield from connection.flush()

        self.qubits[0] = yield from self.distributed_cnot_target(
            self.qubits[0], "Alice", context, connection
            )

        if self.apply_H:
            self.qubits[0].H()

        result = self.qubits[0].measure()
        yield from connection.flush()

        return int(result)


if __name__ == "__main__":
    num_shots = 100

    node_names = ["Alice", "Bob", "Charlie"]

    cfg = create_complete_graph_network(
        node_names,
        "perfect",
        PerfectLinkConfig(state_delay=100),
        clink_typ="default",
        clink_cfg=DefaultCLinkConfig(delay=100),
    )


    possible_outcomes = ["000", "001", "010", "011", "100", "101", "110", "111"]

    programs = {
        "Alice": Alice(apply_H=True, name="Alice", peers=["Bob", "Charlie"], qubits=2),
        "Bob": Bob(name="Bob", peers=["Alice"], qubits=2),
        "Charlie": Charlie(name="Charlie", peers=["Alice"], qubits=2)
        }

    out = run(config=cfg, programs=programs, num_times=num_shots)
    outcomes_zxx = outcomes = ["".join(str(out[i][j]) for i in range(3)) for j in range(num_shots)]

    programs = {
        "Alice": Alice(name="Alice", peers=["Bob", "Charlie"], qubits=2),
        "Bob": Bob(apply_H=True, name="Bob", peers=["Alice"], qubits=2),
        "Charlie": Charlie(name="Charlie", peers=["Alice"], qubits=2)
        }

    out = run(config=cfg, programs=programs, num_times=num_shots)
    outcomes_xzx = outcomes = ["".join(str(out[i][j]) for i in range(3)) for j in range(num_shots)]

    programs = {
        "Alice": Alice(name="Alice", peers=["Bob", "Charlie"], qubits=2),
        "Bob": Bob(name="Bob", peers=["Alice"], qubits=2),
        "Charlie": Charlie(apply_H=True, name="Charlie", peers=["Alice"], qubits=2)
        }

    out = run(config=cfg, programs=programs, num_times=num_shots)
    outcomes_xxz = outcomes = ["".join(str(out[i][j]) for i in range(3)) for j in range(num_shots)]

    programs = {
        "Alice": Alice(apply_H=True, name="Alice", peers=["Bob", "Charlie"], qubits=2),
        "Bob": Bob(apply_H=True, name="Bob", peers=["Alice"], qubits=2),
        "Charlie": Charlie(apply_H=True, name="Charlie", peers=["Alice"], qubits=2)
        }

    out = run(config=cfg, programs=programs, num_times=num_shots)
    outcomes_zzz = outcomes = ["".join(str(out[i][j]) for i in range(3)) for j in range(num_shots)]

    outcomes = {
        "ZXX": {p: outcomes_zxx.count(p) for p in possible_outcomes},
        "XZX": {p: outcomes_xzx.count(p) for p in possible_outcomes},
        "XXZ": {p: outcomes_xxz.count(p) for p in possible_outcomes},
        "ZZZ": {p: outcomes_zzz.count(p) for p in possible_outcomes}
    }

    # outcomes_format = [[outcomes[out], out] for out in outcomes]

    print(outcomes)
