import numpy as np

from cryptography.hazmat.primitives import hashes, hmac

from netqasm.sdk.classical_communication.socket import Socket
from netqasm.sdk.epr_socket import EPRSocket
from netqasm.sdk.qubit import Qubit

from netsquid_magic.models.perfect import PerfectLinkConfig
from netsquid_netbuilder.modules.clinks.default import DefaultCLinkConfig
from netsquid_netbuilder.util.network_generation import create_complete_graph_network

from squidasm.run.stack.run import run
from squidasm.sim.stack.program import ProgramContext

from AbstractNode import AbstractNode

import hmac
import hashlib


def generate_hmac(key, message):
    """
    Generate HMAC authentication code from two strings of bits.

    Parameters:
    - key (bytes): The secret key for HMAC.
    - message (bytes): The message to authenticate.

    Returns:
    - str: The binary representation of HMAC authentication code.
    """
    # Choose the hash function, here we use SHA-256
    hash_function = hashlib.sha256

    # Create an HMAC object with the key and chosen hash function
    hmac_generator = hmac.new(key, message, hash_function)

    # Obtain the HMAC authentication code in binary format
    hmac_code_binary = bin(int(hmac_generator.hexdigest(), 16))[2:].zfill(8 * (len(hmac_generator.digest()) // 2))

    return hmac_code_binary


class Bank(AbstractNode):
    shared_secret = np.array([1, 0, 0, 1])
    len_key = len(shared_secret)

    def run(self, context: ProgramContext):
        connection = context.connection

        basis = np.random.choice([0, 1], self.len_key)
        
        basis = np.array([1, 0, 0, 0])
        value = np.random.choice([0, 1], self.len_key)

        for i, (b, v) in enumerate(zip(basis, value)):
            self.qubits[i] = Qubit(connection)
            if v:
                self.qubits[i].X()
            if b:
                self.qubits[i].H()
            
            yield from self.teleport_data_send(
                self.qubits[i], self.peers[0], context, connection)

            self.qubits[i] = Qubit(connection)
            if v:
                self.qubits[i].X()
            if b:
                self.qubits[i].H()

        result = np.zeros(self.len_key)
        for i, b in enumerate(basis):
            if b:
                self.qubits[i].H()
            res = self.qubits[i].measure()
            yield from connection.flush()
            result[i] = int(res)

        return result


class Client(AbstractNode):
    shared_secret = np.array([1, 0, 0, 1])
    len_key = len(shared_secret)

    def run(self, context: ProgramContext):
        connection = context.connection

        merchant = "Merchant1"

        for i in range(self.len_key):
            self.qubits[i] = yield from self.teleport_data_recv(
                "Bank", context, connection
                )

        vendor_id = MERCHANT_IDS[merchant]
        
        hmac = generate_hmac(
            self.shared_secret, vendor_id)
        print(hmac)

        """ CHECK """
        basis = [1, 0, 0, 1]
        result = np.zeros(self.len_key)
        for i, b in enumerate(basis):
            if b:
                self.qubits[i].H()
            res = self.qubits[i].measure()
            yield from connection.flush()
            result[i] = int(res)

        return result


class Merchant(AbstractNode):
    # def __init__(self, *args, len_key=4, **kwargs):
    #     self.len_key = len_key
    #     super().__init__(*args, **kwargs)

    def run(self, context: ProgramContext):
        connection = context.connection

        # self.qubits[0] = Qubit(connection)
        # result = self.qubits[0].measure()
        # yield from connection.flush()

        # return int(result)
        return


if __name__ == "__main__":
    num_nodes = 3
    num_shots = 1
    num_merchants = 3
    len_key = 4
    chosen_merchant = "Merchant1"

    global MERCHANT_IDS
    merchants = [f"Merchant{i}" for i in range(num_merchants)]
    MERCHANT_IDS = {m: np.random.choice([0, 1], len_key) for m in merchants}

    # node_names = ["Bank", "Client"] + merchants
    node_names = ["Bank", "Client"]

    cfg = create_complete_graph_network(
        node_names,
        "perfect",
        PerfectLinkConfig(state_delay=100),
        clink_typ="default",
        clink_cfg=DefaultCLinkConfig(delay=100),
    )

    programs = {
        "Bank": Bank(name="Bank", peers=["Client"], qubits=len_key),
        "Client": Client(name="Client", peers=["Bank"], qubits=len_key)
        }
    # programs.update({
    #     n: Merchant(len_key=len_key, name=n, peers=["Bank", "Client"], qubits=1) for n in merchants})

    out = run(config=cfg, programs=programs, num_times=num_shots)
    print(out)
    # outcomes = ["".join(str(out[i][j]) for i in range(num_nodes)) for j in range(num_shots)]

    # print(outcomes)
