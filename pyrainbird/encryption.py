import sys

from Crypto import Random
from Crypto.Cipher import AES
from Crypto.Hash import SHA256

BLOCK_SIZE = 16
INTERRUPT = "\x00"
PAD = "\x10"


def _add_padding(data):
    new_data = data
    new_data_len = len(new_data)
    remaining_len = BLOCK_SIZE - new_data_len
    to_pad_len = remaining_len % BLOCK_SIZE
    pad_string = PAD * to_pad_len
    return "".join([new_data, pad_string])


def decrypt(encrypted_data, decrypt_key):
    iv = bytes(encrypted_data[32:48])
    encrypted_data = bytes(encrypted_data[48 : len(encrypted_data)])

    m = SHA256.new()
    m.update(to_bytes(decrypt_key))

    symmetric_key = m.digest()
    symmetric_key = symmetric_key[:32]

    aes_decryptor = AES.new(symmetric_key, AES.MODE_CBC, iv)
    return aes_decryptor.decrypt(encrypted_data)


def encrypt(data, encryptkey):
    tocodedata = data + "\x00\x10"
    m = SHA256.new()
    m.update(to_bytes(encryptkey))
    b = m.digest()
    iv = Random.new().read(16)
    c = to_bytes(_add_padding(tocodedata))
    m = SHA256.new()
    m.update(to_bytes(data))
    b2 = m.digest()

    eas_encryptor = AES.new(b, AES.MODE_CBC, iv)
    encrypteddata = eas_encryptor.encrypt(c)
    return b2 + iv + encrypteddata


def to_bytes(string):
    return (
        to_bytes_old(string)
        if sys.version_info < (3, 0)
        else bytes(string, "UTF-8")
    )


def to_bytes_old(string):
    return bytes(string.encode("UTF-8"))
