"""
This is a sample HTTP server interface with the GPUSim backend,
which takes fingerprints as a JSON and returns results in JSON form.

THIS RUNS ON PORT 80 AND IS NOT SECURE.  For production use you should wrap
using nginx or equivalent and only use https externally.
"""

import os
import random
import subprocess
import sys
import time
import tempfile

from PyQt5 import QtCore, QtNetwork

from socketserver import ThreadingMixIn

import cgi
import json

import gpusim_utils

SCRIPT_DIR = os.path.split(__file__)[0]
BITCOUNT = 1024

socket = None

# Make sure there's only ever a single search at a time
search_mutex = QtCore.QMutex()

try:
    from gpusim_server_loc import GPUSIM_EXEC  # Used in schrodinger env
except ImportError:
    script_path = os.path.split(__file__)[0]
    GPUSIM_EXEC = os.path.join(script_path, '..', 'gpusimserver')



def get_data(dbnames, dbkeys, src_smiles, return_count,
             similarity_cutoff, request_num):
    global socket
    fp_binary, canon_smile = gpusim_utils.smiles_to_fingerprint_bin(src_smiles)
    fp_qba = QtCore.QByteArray(fp_binary)

    output_qba = QtCore.QByteArray()
    output_qds = QtCore.QDataStream(output_qba, QtCore.QIODevice.WriteOnly)

    output_qds.writeInt(len(dbnames))
    for name, key in zip(dbnames, dbkeys):
        output_qds.writeString(name.encode())
        output_qds.writeString(key.encode())
    
    output_qds.writeInt(request_num)
    output_qds.writeInt(return_count)
    output_qds.writeFloat(similarity_cutoff)
    output_qds << fp_qba

    socket.write(output_qba)
    socket.flush()
    socket.waitForReadyRead(30000)

    output_qba = socket.readAll()
    return output_qba

def flush_socket():
    global socket
    while not socket.atEnd():
        socket.readAll()

def deserialize_results(request_num, output_qba):
    data_reader = QtCore.QDataStream(output_qba)
    returned_request = data_reader.readInt()
    print(returned_request)
    print(request_num)
    if request_num != returned_request:
        raise RuntimeError("Incorrect result ID returned!")
    return_count = data_reader.readInt()
    approximate_matches = data_reader.readUInt64()
    smiles, ids, scores = [], [], []
    for i in range(return_count):
        smiles.append(data_reader.readString().decode("utf-8"))
    for i in range(return_count):
        ids.append(data_reader.readString().decode("utf-8"))
    for i in range(return_count):
        scores.append(data_reader.readFloat())
    return approximate_matches, return_count, smiles, ids, scores

def search_for_results(src_smiles, return_count, similarity_cutoff, dbnames, dbkeys):
    global search_mutex
    search_mutex.lock()
    try:
        request_num = random.randint(0, 2**31)
        print("Processing request {0}".format(request_num),
              file=sys.stderr) #noqa
        output_qba = get_data(dbnames, dbkeys, src_smiles,
                                   return_count, similarity_cutoff,
                                   request_num)
        try:
            approximate_results, return_count, smiles, ids, scores = \
                deserialize_results(request_num, output_qba)
        except RuntimeError:
            flush_socket()
            raise

        return approximate_results, smiles, ids, scores, src_smiles
    finally:
        search_mutex.unlock()

def parse_args():
    import argparse
    parser = argparse.ArgumentParser(description="Sample GPUSim Server - "
            "run an HTTP server that loads fingerprint data onto GPU and " #noqa
            "responds to queries to find most similar fingperints.") #noqa
    parser.add_argument('--dbnames', help=".fsim files containing fingerprint "
                        "data to be searched", nargs='*')
    parser.add_argument('--dbkeys', help=" ", default="", nargs='*')
    parser.add_argument('--sm_file', help="file with SMILES queries "
                        "to be processed")
    parser.add_argument('--cutoff', help="similarity cutoff", type=float, default=0.8)
    parser.add_argument('--return_count', help="numer of results "
                        "to be searched", type=int, default=20)
    parser.add_argument('--gpu_bitcount', default='0',
                        help="Provide the maximum bitcount for fingerprints on GPU") #noqa
    parser.add_argument('--debug', action='store_true', help="Run the backend inside GDB") #noqa
    return parser.parse_args()


def setup_socket(app):
    global socket

    socket = QtNetwork.QLocalSocket(app)
    while not socket.isValid():
        socket_name = 'gpusimilarity'
        socket.connectToServer(socket_name)
        time.sleep(0.3)


def main():

    args = parse_args()
    db = args.dbnames
    #all_dbs = args.dbnames
    f = open(args.sm_file)
    mol_list = []
    for line in f:
        mol_list.append(line[:-1])
    similarity_cutoff = args.cutoff
    return_count = args.return_count
    # Try to connect to the GPU backend
    app = QtCore.QCoreApplication([])
    cmdline = [GPUSIM_EXEC]
    cmdline += ['--gpu_bitcount', args.gpu_bitcount]
    cmdline += db
    backend_proc = subprocess.Popen(cmdline)
    setup_socket(app)
    for mol in mol_list:
        approximate_results, smiles, ids, scores, src_smiles = \
        search_for_results(mol, return_count, similarity_cutoff, ["default"], [""])
        backend_proc.kill()
        
if __name__ == '__main__':
    main()
