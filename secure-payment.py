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
    hmac_code_binary = bin(int(hmac_generator.hexdigest(), 16))[2:].zfill(4*len(hmac_generator.digest()))

    return hmac_code_binary


def hex_to_binary(hex_str):
    # Obtain the HMAC authentication code in binary format
    return bin(int(hex_str, 16))[2:].zfill(4*len(hex_str))


class Bank(AbstractNode):
    def __init__(self, client: str, merchant: str, *args, **kwargs):
        super().__init__(*args, peers=[client, merchant], **kwargs)
        self.client = client
        self.merchant = merchant

    def run(self, context: ProgramContext):
        connection = context.connection

        basis = np.random.choice([0, 1], KEY_LENGTH)
        value = np.random.choice([0, 1], KEY_LENGTH)

        for i, (b, v) in enumerate(zip(basis, value)):
            self.qubits[i] = Qubit(connection)
            if v:
                self.qubits[i].X()
            if b:
                self.qubits[i].H()
            
            yield from self.teleport_data_send(
                self.qubits[i], self.peers[0], context, connection)

        csocket_merchant = context.csockets[self.merchant]
        msg = yield from csocket_merchant.recv()
        client_id, result, merchant_id = msg.split(",")

        hmac = generate_hmac(
            CLIENT_SHARED_SECRET[client_id].encode('ascii'),
            merchant_id.encode('ascii')
        )

        if len(hmac) > KEY_LENGTH:
            basis_verify = hmac[0:KEY_LENGTH]
        elif len(hmac) < KEY_LENGTH:
            raise Exception(f"len_key > {len(hmac)}")
        else:
            basis_verify = hmac

        list_coincidences = [int(i) == int(j) for i, j in zip(basis_verify, basis)]
        print(list_coincidences)

        verify_coincidences = [
            int(v) == int(r)
            for v, r, b1, b2 in zip(value, result, basis, basis_verify)
            if int(b1) == int(b2)]
        print(verify_coincidences)

        """ NOT NECESSARY, KEPT FOR ENTANGLEMENT PROTOCOL
        result_verify = np.zeros(KEY_LENGTH, dtype=int)
        for i, b in enumerate(basis_verify):
            self.qubits[i] = Qubit(connection)
            if b:
                self.qubits[i].H()
            res = self.qubits[i].measure()
            yield from connection.flush()
            result_verify[i] = res
        """

        return value


class Client(AbstractNode):
    def __init__(self, merchant, shared_secret, *args, **kwargs):
        super().__init__(*args, peers=["Bank", merchant], **kwargs)
        self.merchant = merchant
        self.shared_secret = shared_secret

    def run(self, context: ProgramContext):
        connection = context.connection

        for i in range(KEY_LENGTH):
            self.qubits[i] = yield from self.teleport_data_recv(
                "Bank", context, connection
                )

        hmac = generate_hmac(
            self.shared_secret.encode('ascii'),
            MERCHANT_IDS[self.merchant].encode('ascii')
        )

        if len(hmac) > KEY_LENGTH:
            basis = hmac[0:KEY_LENGTH]
        elif len(hmac) < KEY_LENGTH:
            raise Exception(f"len_key > {len(hmac)}")
        else:
            basis = hmac

        result = np.zeros(KEY_LENGTH, dtype=int)
        for i, b in enumerate(basis):
            if b:
                self.qubits[i].H()
            res = self.qubits[i].measure()
            yield from connection.flush()
            result[i] = res

        result_str = "".join(str(r) for r in result)

        csocket = context.csockets[self.merchant]
        msg = f"{CLIENT_IDS[self.name]},{result_str}"
        csocket.send(msg)
        yield from connection.flush()

        return result


class Merchant(AbstractNode):       
        # RECEIVE -
        # receives C,k from Client
        # but C is public. 
        # so receives only k

        # SEND - 
        # sends C, k, M to Bank
        # But C,M is public
        # so sends only k

    def __init__(self, *args, client: str, **kwargs):
        super().__init__(*args, peers=["Bank", client], **kwargs)
        self.client = client

    def run(self, context: ProgramContext):
        connection = context.connection
        csocket_client = context.csockets[self.client]

        msg = yield from csocket_client.recv()
        msg += f",{MERCHANT_IDS[self.name]}"
        # print(msg)

        csocket_bank = context.csockets["Bank"]
        csocket_bank.send(msg)
        yield from connection.flush()


if __name__ == "__main__":
    num_nodes = 3
    num_shots = 1
    num_merchants = 3
    chosen_client = "Iago"
    chosen_merchant = "Atadana"

    global KEY_LENGTH, CLIENT_IDS, MERCHANT_IDS
    merchants = ["Atadana", "Priya", "Iago"]
    clients = ["Atadana", "Priya", "Iago"]
    KEY_LENGTH = 16
    MERCHANT_IDS = {
        n: ("".join(i for i in np.random.choice(['0', '1'], KEY_LENGTH))) for n in merchants}
    CLIENT_IDS = {
        n: ("".join(i for i in np.random.choice(['0', '1'], KEY_LENGTH))) for n in clients}
    CLIENT_SHARED_SECRET = {
        CLIENT_IDS[n]: ("".join(i for i in np.random.choice(['0', '1'], KEY_LENGTH))) for n in CLIENT_IDS.keys()}

    node_names = ["Bank", chosen_client, chosen_merchant]

    cfg = create_complete_graph_network(
        node_names,
        "perfect",
        PerfectLinkConfig(state_delay=100),
        clink_typ="default",
        clink_cfg=DefaultCLinkConfig(delay=100),
    )

    programs = {
        "Bank": Bank(
            name="Bank",
            client=chosen_client,
            merchant=chosen_merchant,
            qubits=KEY_LENGTH),
        chosen_client: Client(
            name=chosen_client,
            merchant=chosen_merchant,
            shared_secret=CLIENT_SHARED_SECRET[CLIENT_IDS[chosen_client]],
            qubits=KEY_LENGTH),
        chosen_merchant: Merchant(
            name=chosen_merchant,
            client=chosen_client)
        }

    out = run(config=cfg, programs=programs, num_times=num_shots)
    print(out)
    # outcomes = ["".join(str(out[i][j]) for i in range(num_nodes)) for j in range(num_shots)]

    # print(outcomes)
