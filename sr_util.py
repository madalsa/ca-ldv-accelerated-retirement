# Ensure compatibility between python 2 and python 3
from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import requests
import platform
import os
import stat
import tempfile
import json
import time
import subprocess
import geopandas as gpd
import shutil

def _download(url, file_name):
    # open in binary mode
    with open(file_name, "wb") as file:
        # get request
        response = requests.get(url)
        if not response.ok:
            raise Exception("Downloading file from {} failed".format(url))
        # write to file
        file.write(response.content)

_inmap_exe = None
_tmpdir = tempfile.TemporaryDirectory()

def run_sr(emis, model, output_variables, emis_units="tons/year"):
    """
    Run the provided emissions through the specified SR matrix, calculating the
    specified output properties.

    Args:
        emis: The emissions to be calculated, Needs to be a geopandas dataframe.

        model: The SR matrix to use. Allowed values:
            isrm: The InMAP SR matrix
            apsca_q0: The APSCA SR matrix, annual average
            apsca_q1: The APSCA SR matrix, Jan-Mar season
            apsca_q2: The APSCA SR matrix, Apr-Jun season
            apsca_q3: The APSCA SR matrix, Jul-Sep season
            apsca_q4: The APSCA SR matrix, Oct-Dec season

        output_variables: Output variables to be calculated. See
            https://inmap.run/docs/results/ for more information.

        emis_units: The units that the emissions are in. Allowed values:
            'tons/year', 'kg/year', 'ug/s', and 'μg/s'.
    """

    global _tmpdir
    global _inmap_exe

    model_paths = {
        "isrm": "isrm_v1.2.1.ncf",
        "apsca_q0": "/data/apsca/apsca_sr_Q0_v1.2.1.ncf",
        "apsca_q1": "/data/apsca/apsca_sr_Q1_v1.2.1.ncf",
        "apsca_q2": "/data/apsca/apsca_sr_Q2_v1.2.1.ncf",
        "apsca_q3": "/data/apsca/apsca_sr_Q3_v1.2.1.ncf",
        "apsca_q4": "/data/apsca/apsca_sr_Q4_v1.2.1.ncf",
    }
    if model not in model_paths.keys():
        models = ', '.join("{!s}".format(k) for (k) in model_paths.keys())
        msg = 'model must be one of \{{!s}\}, but is `{!s}`'.format(models, model)
        raise ValueError(msg)
    model_path = model_paths[model]

    start = time.time()
    job_name = "run_aqm_%s" % start

    # Create a temp directory for this run's input and output
    job_dir = os.path.join(_tmpdir.name, job_name)
    os.makedirs(job_dir, exist_ok=True)

    emis_file = os.path.join(job_dir, "emissions.shp")
    output_file = os.path.join(job_dir, "OutputFile.shp")
    emis.to_file(emis_file)

    arch = platform.machine()

    if arch == "x86_64": arch = "amd64"
    if arch == "arm64": arch = "arm64"

    version = "1.9.6"

    if _inmap_exe is None:
        ost = platform.system()
        print("Downloading InMAP executable for %s               " % ost, end='\r')
        if ost == "Windows":
            _inmap_exe = os.path.join(_tmpdir.name, "inmap_%s.exe" % version)
            _download("https://github.com/spatialmodel/inmap/releases/download/v%s/inmap-v%s-windows-%s.exe" % (version, version, arch), _inmap_exe)
        elif ost == "Darwin":
            _inmap_exe = os.path.join(_tmpdir.name, "inmap_%s" % version)
            _download("https://github.com/spatialmodel/inmap/releases/download/v%s/inmap-v%s-darwin-%s" % (version, version, arch), _inmap_exe)
        elif ost == "Linux":
            _inmap_exe = os.path.join(_tmpdir.name, "inmap_%s" % version)
            _download("https://github.com/spatialmodel/inmap/releases/download/v%s/inmap-v%s-linux-%s" % (version, version, arch), _inmap_exe)
        else:
            raise(OSError("invalid operating system %s" % (ost)))
        os.chmod(_inmap_exe, stat.S_IXUSR | stat.S_IRUSR | stat.S_IWUSR)

    # Run InMAP srpredict locally with explicit output path
    subprocess.check_output([_inmap_exe, "srpredict",
       "--EmissionUnits=%s" % emis_units,
       "--EmissionsShapefiles=%s" % emis_file,
       "--OutputVariables=%s" % json.dumps(output_variables),
       "--OutputFile=%s" % output_file,
       "--SR.OutputFile=%s" % model_path])

    output = gpd.read_file(output_file)

    # Clean up temp files for this run to free disk space
    shutil.rmtree(job_dir, ignore_errors=True)

    return output
