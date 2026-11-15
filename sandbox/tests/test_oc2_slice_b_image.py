from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from oc2_slice_b_image import (ImagePin, SliceBImageRejected, verify_build_inputs,
                                  verify_image_archive, verify_loaded_image,
                                  verify_runtime_pin_against_manifest,offline_build_argv)

class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.raw=b'test archive'
        self.archive=self.root/'writer-image.tar';self.archive.write_bytes(self.raw)
        self.ref='oc2/slice-b@sha256:'+'a'*64
        self.config='sha256:'+'b'*64
        self.pin=ImagePin('f'*40,'c'*64,'d'*64,self.ref,self.config,hashlib.sha256(self.raw).hexdigest())
        self.inspect={'Id':self.config,'RepoDigests':[self.ref],
                      'Config':{'Entrypoint':['/opt/oc2/slice-b/entrypoint'],
                                'Cmd':['run'],'User':'10001:10001','WorkingDir':'/workspace','Env':[]}}

    def test_matching_local_digest(self):
        verify_image_archive(self.archive,self.pin)
        verify_loaded_image(self.inspect,self.pin)
        verify_runtime_pin_against_manifest(self.pin,'d'*64)

    def test_reject_bare_config_id_or_tag(self):
        from dataclasses import replace
        for ref in ('sha256:'+'a'*64,'oc2/slice-b:latest'):
            with self.assertRaises(SliceBImageRejected):verify_loaded_image(self.inspect,replace(self.pin,image_ref=ref))

    def test_reject_repo_digest_missing(self):
        d={**self.inspect,'RepoDigests':[]}
        with self.assertRaises(SliceBImageRejected):verify_loaded_image(d,self.pin)

    def test_reject_image_config_id_mismatch(self):
        with self.assertRaises(SliceBImageRejected):verify_loaded_image({**self.inspect,'Id':'sha256:'+'f'*64},self.pin)

    def test_archive_tamper(self):
        self.archive.write_bytes(self.raw+b'tampered')
        with self.assertRaises(SliceBImageRejected):verify_image_archive(self.archive,self.pin)

    def test_runtime_digest_is_independent(self):
        with self.assertRaises(SliceBImageRejected):verify_runtime_pin_against_manifest(self.pin,'e'*64)

    def test_unpinned_build_inputs_blocked(self):
        with self.assertRaises(SliceBImageRejected):verify_build_inputs(self.root)

if __name__=='__main__':unittest.main()
