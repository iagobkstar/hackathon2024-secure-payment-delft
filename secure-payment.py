import numpy as np
import hmac
import hashlib

from netqasm.sdk.classical_communication.socket import Socket
from netqasm.sdk.epr_socket import EPRSocket
from netqasm.sdk.qubit import Qubit

from netsquid_magic.models.perfect import PerfectLinkConfig
from netsquid_netbuilder.modules.clinks.default import DefaultCLinkConfig
from netsquid_netbuilder.util.network_generation import create_complete_graph_network
from netsquid_netbuilder.modules.qdevices.generic import GenericQDeviceConfig

from squidasm.run.stack.run import run
from squidasm.sim.stack.program import ProgramContext

from squidasm.util.util import get_qubit_state

from AbstractNode import AbstractNode



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

        original_basis = "".join(str(r) for r in basis)
        original_value= "".join(str(r) for r in value)

        for i, (b, v) in enumerate(zip(basis, value)):
            self.qubits[i] = Qubit(connection)

            if v:
                self.qubits[i].X()
            if b:
                self.qubits[i].H()
            yield from connection.flush()

            yield from self.teleport_data_send(
                self.qubits[i], self.peers[0], context, connection)

        csocket_merchant = context.csockets[self.merchant]
        msg = yield from csocket_merchant.recv()
        client_id, measured_value, merchant_id = msg.split(",")

        hmac = generate_hmac(
            CLIENT_SHARED_SECRET[client_id].encode('ascii'),
            merchant_id.encode('ascii')
        )

        if len(hmac) > KEY_LENGTH:
            measured_basis = hmac[0:KEY_LENGTH]
        elif len(hmac) < KEY_LENGTH:
            raise Exception(f"len_key > {len(hmac)}")
        else:
            measured_basis = hmac

        measured_basis = "".join(str(r) for r in measured_basis)
        coincidences =  np.array([
            (b1 == b2) for b1, b2 in zip(measured_basis, original_basis)])

        original_basis_array = np.array([i for i in original_basis])
        original_value_array = np.array([i for i in original_value])
        measured_basis_array = np.array([i for i in measured_basis])
        measured_value_array = np.array([i for i in measured_value])

        print(f"r1: {original_value} -> {original_value_array[coincidences]}")
        print(f"b1: {original_basis} -> {original_basis_array[coincidences]}")
        print(f"r2: {measured_value} -> {measured_value_array[coincidences]}")
        print(f"b2: {measured_basis} -> {measured_basis_array[coincidences]}")
        print(f"co: {coincidences}")

        verify_coincidences = [
            (r1 == r2)
            for r1, r2 in zip(
                original_value_array[coincidences],
                measured_value_array[coincidences])]

        if all(verify_coincidences):
            msg = "Transaction accepted"
        else:
            msg = "Transaction rejected"

        csocket_merchant.send(msg)

        return


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

        result = "".join(str(r) for r in result)
        basis = "".join(str(r) for r in basis)

        csocket = context.csockets[self.merchant]
        msg = f"{CLIENT_IDS[self.name]},{result}"
        csocket.send(msg)

        return


class Merchant(AbstractNode):       
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

        msg = yield from csocket_bank.recv()
        print(f"Outcome: {msg}")

        return msg


if __name__ == "__main__":
    num_shots = 5
    chosen_client = "Iago"
    chosen_merchant = "Atadana"

    global KEY_LENGTH, CLIENT_IDS, MERCHANT_IDS
    merchants = ["Atadana", "Priya", "Iago", "Thijs"]
    clients = ["Atadana", "Priya", "Iago", "Thijs"]
    KEY_LENGTH = 32
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
        qdevice_cfg=GenericQDeviceConfig.perfect_config(num_qubits=KEY_LENGTH),
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

    _, _, _ = run(config=cfg, programs=programs, num_times=num_shots)
