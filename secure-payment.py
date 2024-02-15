from netqasm.sdk.classical_communication.socket import Socket
from netqasm.sdk.epr_socket import EPRSocket
from netqasm.sdk.qubit import Qubit

from netsquid_magic.models.perfect import PerfectLinkConfig
from netsquid_netbuilder.modules.clinks.default import DefaultCLinkConfig
from netsquid_netbuilder.util.network_generation import create_complete_graph_network

from squidasm.run.stack.run import run
from squidasm.sim.stack.program import ProgramContext

from AbstractNode import AbstractNode


class Bank(AbstractNode):
    def run(self, context: ProgramContext):
        connection = context.connection

        self.qubits[0] = Qubit(connection)
        result = self.qubits[0].measure()
        yield from connection.flush()

        return int(result)

class Client(AbstractNode):
    def run(self, context: ProgramContext):
        connection = context.connection

        self.qubits[0] = Qubit(connection)
        result = self.qubits[0].measure()
        yield from connection.flush()

        return int(result)

class Merchant(AbstractNode):
    def run(self, context: ProgramContext):
        connection = context.connection

        self.qubits[0] = Qubit(connection)
        result = self.qubits[0].measure()
        yield from connection.flush()

        return int(result)


if __name__ == "__main__":
    num_nodes = 3
    num_shots = 1

    node_names = ["Bank", "Client", "Merchant"]
    cfg = create_complete_graph_network(
        node_names,
        "perfect",
        PerfectLinkConfig(state_delay=100),
        clink_typ="default",
        clink_cfg=DefaultCLinkConfig(delay=100),
    )

    programs = {
        "Bank": Bank(name="Bank", peers=["Client", "Merchant"], qubits=2),
        "Client": Client(name="Client", peers=["Bank", "Merchant"], qubits=2),
        "Merchant": Merchant(name="Merchant", peers=["Bank", "Client"], qubits=1)
    }

    out = run(config=cfg, programs=programs, num_times=num_shots)
    outcomes = ["".join(str(out[i][j]) for i in range(num_nodes)) for j in range(num_shots)]

    print(outcomes)
