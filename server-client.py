from typing import List

import netsquid as ns
from netqasm.sdk.classical_communication.socket import Socket
from netqasm.sdk.connection import BaseNetQASMConnection
from netqasm.sdk.epr_socket import EPRSocket

from netsquid_magic.models.perfect import PerfectLinkConfig
from netsquid_netbuilder.modules.clinks.default import DefaultCLinkConfig
from netsquid_netbuilder.util.network_generation import create_complete_graph_network

from squidasm.run.stack.run import run
from squidasm.sim.stack.program import Program, ProgramContext, ProgramMeta


class ClientProgram(Program):
    def __init__(self, name: str, server_name: str):
        self.name = name
        self.server_name = server_name

    @property
    def meta(self) -> ProgramMeta:
        return ProgramMeta(
            name="tutorial_program",
            csockets=[self.server_name],
            epr_sockets=[self.server_name],
            max_qubits=1,
        )

    def run(self, context: ProgramContext):
        # get classical socket to peer
        csocket = context.csockets[self.server_name]
        # get EPR socket to peer
        epr_socket = context.epr_sockets[self.server_name]
        # get connection to quantum network processing unit
        connection = context.connection

        # Bob listens for messages on his classical socket
        message = yield from csocket.recv()
        print(f"{ns.sim_time()} ns: Client: {self.name} receives message: {message}")

        # Listen for request to create EPR pair, apply a Hadamard gate on the epr qubit and measure
        epr_qubit = epr_socket.recv_keep()[0]
        epr_qubit.H()
        result = epr_qubit.measure()
        yield from connection.flush()
        print(
            f"{ns.sim_time()} ns: Client: {self.name} measures local EPR qubit: {result}"
        )

        return {}


class ServerProgram(Program):
    def __init__(self, clients: List[str]):
        self.clients = clients

    @property
    def meta(self) -> ProgramMeta:
        return ProgramMeta(
            name="tutorial_program",
            csockets=self.clients,
            epr_sockets=self.clients,
            max_qubits=1,
        )

    def run(self, context: ProgramContext):
        connection: BaseNetQASMConnection = context.connection

        for client in self.clients:
            # get classical socket to peer
            csocket: Socket = context.csockets[client]
            epr_socket: EPRSocket = context.epr_sockets[client]

            # send a string message via a classical channel
            message = f"Client: {client} you may start"
            csocket.send(message)
            print(f"{ns.sim_time()} ns: Server sends message: {message}")

            # Register a request to create an EPR pair, then apply a Hadamard gate on the epr qubit and measure
            epr_qubit = epr_socket.create_keep()[0]
            epr_qubit.H()
            result = epr_qubit.measure()
            yield from connection.flush()
            print(f"{ns.sim_time()} ns: Server measures local EPR qubit: {result}")

        return {}


if __name__ == "__main__":
    num_nodes = 6
    node_names = [f"Node_{i}" for i in range(num_nodes)]

    # import network configuration from file
    cfg = create_complete_graph_network(
        node_names,
        "perfect",
        PerfectLinkConfig(state_delay=100),
        clink_typ="default",
        clink_cfg=DefaultCLinkConfig(delay=100),
    )

    server_name = node_names[0]
    client_names = node_names[1:]
    # Create instances of programs to run

    programs = {server_name: ServerProgram(clients=client_names)}
    for client in client_names:
        programs[client] = ClientProgram(client, server_name)

    # Run the simulation. Programs argument is a mapping of network node labels to programs to run on that node
    run(config=cfg, programs=programs, num_times=1)
