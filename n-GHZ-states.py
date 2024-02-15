from netqasm.sdk.classical_communication.socket import Socket
from netqasm.sdk.epr_socket import EPRSocket
from netqasm.sdk.qubit import Qubit

from netsquid_magic.models.perfect import PerfectLinkConfig
from netsquid_netbuilder.modules.clinks.default import DefaultCLinkConfig
from netsquid_netbuilder.util.network_generation import create_complete_graph_network

from squidasm.run.stack.run import run
from squidasm.sim.stack.program import ProgramContext

from AbstractNode import AbstractNode


class MasterNode(AbstractNode):
    def run(self, context: ProgramContext):
        connection = context.connection

        self.qubits[0] = Qubit(connection)
        self.qubits[0].H()
        yield from connection.flush()

        for peer in self.peers:
            self.qubits[0] = yield from self.distributed_cnot_source(
                self.qubits[0], peer, context, connection
                )

        result = self.qubits[0].measure()
        yield from connection.flush()

        return int(result)


class SlaveNode(AbstractNode):
    def run(self, context: ProgramContext):
        connection = context.connection

        self.qubits[0] = Qubit(connection)
        yield from connection.flush()

        self.qubits[0] = yield from self.distributed_cnot_target(
            self.qubits[0], self.peers[0], context, connection
            )

        result = self.qubits[0].measure()
        yield from connection.flush()

        return int(result)


if __name__ == "__main__":
    num_nodes = 5
    num_shots = 20

    node_names = ["Master"] + [f"Slave{i}" for i in range(num_nodes-1)]
    cfg = create_complete_graph_network(
        node_names,
        "perfect",
        PerfectLinkConfig(state_delay=100),
        clink_typ="default",
        clink_cfg=DefaultCLinkConfig(delay=100),
    )

    programs = {"Master": MasterNode(name=node_names[0], peers=node_names[1:], qubits=2)}
    programs.update({n: SlaveNode(name=n, peers=[node_names[0]], qubits=2) for n in node_names[1:]})

    out = run(config=cfg, programs=programs, num_times=num_shots)
    outcomes = ["".join(str(out[i][j]) for i in range(num_nodes)) for j in range(num_shots)]

    print(outcomes)
