"""Verify actual public release artifacts without importing the development tree."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import venv
import zipfile

base = Path(sys.argv[1]).resolve()
base.mkdir(parents=True, exist_ok=False)
repo = 'waxwingfactor/wl-contract'
tag = 'v1.0.0'

def curl(url, destination):
    result = subprocess.run(['curl','--fail','--location','--silent','--show-error',
                             '--output',str(destination),'--write-out','%{http_code}',url],
                            capture_output=True,text=True,check=True)
    if result.stdout != '200':
        raise AssertionError('non-200 anonymous public fetch: '+result.stdout)

curl('https://api.github.com/repos/'+repo+'/releases/tags/'+tag, base/'release-api.json')
release = json.loads((base/'release-api.json').read_text())
assert release['draft'] is False and release['prerelease'] is False
assets = {asset['name']:asset for asset in release['assets']}
names = ['wl_contract-1.0.0-py3-none-any.whl','wl_contract-1.0.0.tar.gz','PROVENANCE.json','SHA256SUMS']
for name in names:
    curl(assets[name]['browser_download_url'],base/name)
hashes = {}
for line in (base/'SHA256SUMS').read_text().splitlines():
    expected,name = line.split(None,1)
    name = name.lstrip('*')
    assert name in names and '/' not in name
    actual = hashlib.sha256((base/name).read_bytes()).hexdigest()
    assert actual == expected
    assert assets[name]['digest'] == 'sha256:'+actual
    hashes[name] = actual
assert set(hashes) == set(names)-{'SHA256SUMS'}
provenance = json.loads((base/'PROVENANCE.json').read_text())
assert provenance['source_commit'] == '3eac47707b692cfff170be6cfa586ef7633425e1'
sourcehashes = provenance['source_modules_sha256']
with zipfile.ZipFile(base/names[0]) as wheel:
    for filename,digest in sourcehashes.items():
        assert hashlib.sha256(wheel.read(filename.removeprefix('src/'))).hexdigest()==digest
with tarfile.open(base/names[1]) as archive:
    prefix = archive.getmembers()[0].name.split('/')[0]+'/'
    for filename,digest in sourcehashes.items():
        assert hashlib.sha256(archive.extractfile(prefix+filename).read()).hexdigest()==digest
    for member in archive.getmembers():
        assert member.isfile() or member.isdir()
        target=(base/'unpacked'/member.name).resolve()
        assert (base/'unpacked') in target.parents
    archive.extractall(base/'unpacked')
source=next((base/'unpacked').iterdir())
assert (source/'docs/contract.md').is_file()
assert (source/'tests/fixtures/upstream/ext-background-effect.before.xml').is_file()
clean=os.environ.copy()
clean.pop('PYTHONPATH',None)
clean.update(PYTHONNOUSERSITE='1',WL_CONTRACT_TEST_INSTALLED='1',PIP_NO_CACHE_DIR='1',PIP_DISABLE_PIP_VERSION_CHECK='1')
observations=[]
for kind,artifact in [('wheel',base/names[0]),('sdist',base/names[1])]:
    envdir=base/(kind+'-venv')
    venv.EnvBuilder(with_pip=True).create(envdir)
    python=envdir/'bin/python'
    args=[str(python),'-m','pip','install','--no-deps']
    if kind=='wheel': args+=['--no-index']
    subprocess.run(args+[str(artifact)],cwd=base,env=clean,check=True,capture_output=True,text=True)
    check=subprocess.run([str(python),'-I','-c','import wl_contract; print(wl_contract.__file__)'],
                         cwd=base,env=clean,check=True,capture_output=True,text=True)
    assert str(envdir) in check.stdout and '/src/' not in check.stdout
    suite=subprocess.run([str(python),'-I','-m','unittest','discover','-s',str(source/'tests'),'-q'],
                         cwd=base,env=clean,check=True,capture_output=True,text=True)
    assert 'OK' in suite.stderr
    cases=[]
    for name,expected in [('baseline.xml',0),('broken.xml',1),('extended.xml',3)]:
        result=subprocess.run([str(python),'-I','-m','wl_contract','compare',str(source/'examples/baseline.xml'),
                               str(source/'examples'/name),'--format','json'],cwd=base,env=clean,capture_output=True,text=True)
        assert result.returncode==expected,(kind,name,result.stderr)
        cases.append({'input':name,'exit':result.returncode,'verdict':json.loads(result.stdout)['verdict']})
    bad=base/(kind+'-bad.xml');bad.write_text('<!DOCTYPE protocol><protocol name="bad"/>')
    result=subprocess.run([str(python),'-I','-m','wl_contract','compare',str(bad),str(bad),'--format','json'],
                          cwd=base,env=clean,capture_output=True,text=True)
    assert result.returncode==2 and not result.stdout and json.loads(result.stderr)['verdict']=='invalid'
    observations.append({'artifact':kind,'installed_outside_checkout':True,'tests':suite.stderr.strip(),
                         'cases':cases,'invalid_xml_exit':2})
# Relocate inputs and remove all extracted source, tests and docs before the
# installed wheel runs with socket creation blocked and no source search path.
shutil.copytree(source/'examples',base/'inputs-original')
(base/'inputs-original').rename(base/'inputs-relocated')
shutil.rmtree(base/'unpacked')
python=base/'wheel-venv/bin/python'
block='import socket; socket.socket=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("network forbidden")); from wl_contract.__main__ import main; import sys; sys.exit(main(sys.argv[1:]))'
result=subprocess.run([str(python),'-I','-c',block,'compare',str(base/'inputs-relocated/baseline.xml'),
                       str(base/'inputs-relocated/broken.xml'),'--format','json'],cwd=base,env=clean,capture_output=True,text=True)
assert result.returncode==1 and json.loads(result.stdout)['verdict']=='incompatible'
evidence={'release_url':release['html_url'],'tag':tag,'source_commit':provenance['source_commit'],
          'environment':{'python':platform.python_version(),'system':platform.system(),'release':platform.release(),'machine':platform.machine()},
          'anonymous_http_fetches':'200 for metadata and all four requested assets','asset_sha256':hashes,
          'github_asset_digests_matched':True,'wheel_sdist_modules_match_provenance':True,
          'observations':observations,'relocated_inputs_source_removed_socket_blocked':True,
          'behavioral_interoperability_certified':False}
(base/'VERIFICATION.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2))
