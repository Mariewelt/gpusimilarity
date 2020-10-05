for x in /mnt/fsim/part*; do
    mv $x /mnt/fsim/default.fsim
    python3 /gpusimilarity/bld/python/gpusim_no_server.py --dbnames=/mnt/fsim/default.fsim --sm_file=/mnt/fsim/output.smi --cutoff=0.8
    mv /mnt/fsim/default.fsim $x
done
