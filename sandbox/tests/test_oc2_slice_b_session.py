import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
import subprocess

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
from oc2_slice_b_git import admit_clean_repo,build_verified_bundle
from oc2_slice_b_session import (SliceBReceipt, SliceBSessionError, create_session_receipt, update_session_receipt,
                                  verify_session_receipt,import_guest_baseline,verify_guest_authority,build_start_message)

class Key:
    def __init__(self):
        self.workspace_id='a'*32
        self.sandbox_id=str(uuid.uuid4())
        self.session_generation=str(uuid.uuid4())
    def validate(self):
        if len(self.workspace_id)!=32: raise ValueError()
    def __eq__(self,other): return vars(self)==vars(other)


def git(root,*args):
    r=subprocess.run(['git','-C',str(root),*args],capture_output=True)
    if r.returncode: raise AssertionError(r.stderr.decode())


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name)
        self.host=base/'host';self.host.mkdir()
        git(self.host,'init','-b','sliceb')
        git(self.host,'config','user.name','Fixture')
        git(self.host,'config','user.email','fixture@example.invalid')
        (self.host/'hello').write_text('good\n')
        git(self.host,'add','hello');git(self.host,'commit','-m','initial')
        self.key=Key()
        self.baseline=admit_clean_repo(self.host)
        self.art=build_verified_bundle(self.baseline,base/'ref.bundle',key=self.key,runtime_sha256='b'*64)
        self.rec=SliceBReceipt(self.key,self.baseline,self.art.bundle_sha256,self.art.manifest_sha256,
            self.art.transfer_policy_id,'b'*64,'example.test/oc2-writer@sha256:'+'c'*64,
            'sha256:'+'d'*64,'PENDING','NOT_RUN',None,None)
        self.state=base/'state'
        self.guest=base/'guest'

    def test_receipt_create_and_readback(self):
        path=create_session_receipt(self.state,self.rec,self.art)
        self.assertEqual(verify_session_receipt(path,self.key),self.rec)
        with self.assertRaises(SliceBSessionError):
            create_session_receipt(self.state,self.rec,self.art)

    def test_guest_import_and_authority(self):
        path=create_session_receipt(self.state,self.rec,self.art)
        guest=import_guest_baseline(self.art,self.guest,expected_manifest_sha256=self.art.manifest_sha256,
                                   expected_key=self.key,expected_runtime_sha256='b'*64)
        auth=verify_guest_authority(path.parent/'bundle.manifest.json',self.rec,guest,'sha256:'+'d'*64,local_image_inspect={'Id':self.rec.image_config_id,'RepoDigests':[self.rec.image_ref],'Config':{'Entrypoint':['/opt/oc2/slice-b/entrypoint'],'Cmd':['run']}})
        start=build_start_message(auth).to_wire()
        self.assertEqual(start.count(' '),4)
        self.assertTrue(start.endswith('\n'))

    def test_reject_wrong_runtime(self):
        with self.assertRaises(Exception):
            import_guest_baseline(self.art,self.guest,expected_manifest_sha256=self.art.manifest_sha256,
                                  expected_key=self.key,expected_runtime_sha256='e'*64)

    def test_reject_receipt_identity_mutation(self):
        from dataclasses import replace
        path=create_session_receipt(self.state,self.rec,self.art)
        with self.assertRaises(SliceBSessionError):
            update_session_receipt(path,replace(self.rec,runtime_sha256='e'*64))
        self.assertEqual(verify_session_receipt(path,self.key),self.rec)

    def test_reject_guest_control_manifest_mutation(self):
        path=create_session_receipt(self.state,self.rec,self.art)
        guest=import_guest_baseline(self.art,self.guest,expected_manifest_sha256=self.art.manifest_sha256,
                                   expected_key=self.key,expected_runtime_sha256='b'*64)
        p=path.parent/'bundle.manifest.json'
        p.write_bytes(p.read_bytes()+b'X')
        with self.assertRaises(SliceBSessionError):
            verify_guest_authority(p,self.rec,guest,'sha256:'+'d'*64,local_image_inspect={'Id':self.rec.image_config_id,'RepoDigests':[self.rec.image_ref],'Config':{'Entrypoint':['/opt/oc2/slice-b/entrypoint'],'Cmd':['run']}})

if __name__ == '__main__':unittest.main()
