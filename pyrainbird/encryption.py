from Crypto.Hash import SHA256
from Crypto.Cipher import AES
from Crypto import Random

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
    m.update(bytes(decrypt_key, "UTF-8"))

    symmetric_key = m.digest()
    symmetric_key = symmetric_key[:32]

    aes_decryptor = AES.new(symmetric_key, AES.MODE_CBC, iv)
    return aes_decryptor.decrypt(encrypted_data)


def encrypt(data, encryptkey):
    tocodedata = data + "\x00\x10"
    m = SHA256.new()
    m.update(bytes(encryptkey, "UTF-8"))
    b = m.digest()
    iv = Random.new().read(16)
    c = bytes(_add_padding(tocodedata), "UTF-8")
    m = SHA256.new()
    m.update(bytes(data, "UTF-8"))
    b2 = m.digest()

    eas_encryptor = AES.new(b, AES.MODE_CBC, iv)
    encrypteddata = eas_encryptor.encrypt(c)
    return b2 + iv + encrypteddata
