"""Recipient checks exercise stored bytes, not executable archive content."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from certloom.artifact import bundle_members, verify_bundle, write_bundle, MAX_ARCHIVE_BYTES
from certloom.engine import VerificationError, verify_text
from certloom.producer import make_sparse_certificate
from certloom.publication import fresh_output

ROOT = Path(__file__).resolve().parents[1]


def checksum(files):
    files['SHA256SUMS'] = ''.join(sha256(files[n]).hexdigest()+'  '+n+'\n' for n in sorted(files) if n != 'SHA256SUMS').encode()


def archive(path, files, compression=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, 'w', compression) as z:
        for n, b in files.items(): z.writestr(n,b)


class BundleAdmission(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.text = (ROOT/'examples/hilbert8.json').read_text()
        self.files = bundle_members(self.text)

    def check_refused(self, files):
        path=self.root/'mutant.zip'; archive(path,files)
        with self.assertRaises(VerificationError): verify_bundle(path)

    def test_dense_sparse_not_certified_and_undecidable(self):
        docs=[json.loads(self.text), make_sparse_certificate([0,1],[0],[2.],[1.],[.5],[1.])]
        bad=json.loads(self.text);bad['R']=[['0x0.0p+0' for _ in row] for row in bad['R']];docs.append(bad)
        self.assertEqual(verify_text(self.text)['decision']['status'],'undecidable')
        self.assertEqual(verify_text(json.dumps(bad))['status'],'not_certified')
        for i,doc in enumerate(docs):
            text=json.dumps(doc);path=self.root/f'{i}.zip';write_bundle(text,path)
            out=verify_bundle(path);self.assertEqual(out['checksums'],'verified');self.assertEqual(out['result'],verify_text(text))

    def test_rehashed_changed_checker_receipt_or_certificate_rejected(self):
        for mutation in ('checker','receipt','certificate','missing','extra'):
            files=dict(self.files)
            if mutation=='checker': files['checker.py']+=b'\nraise RuntimeError("never run")\n'
            if mutation=='receipt':
                r=json.loads(files['verification.json']);r['result']['status']='fabricated';files['verification.json']=json.dumps(r).encode()
            if mutation=='certificate': files['certificate.json']=files['certificate.json']+b' '
            if mutation=='missing': del files['README.txt']
            if mutation=='extra': files['../escape']=b'x'
            checksum(files);self.check_refused(files)

    def test_checksum_and_duplicate_and_oversize_rejected(self):
        files=dict(self.files); files['README.txt']+=b'changed';self.check_refused(files)
        path=self.root/'duplicate.zip'
        with zipfile.ZipFile(path,'w') as z:
            for name,data in self.files.items(): z.writestr(name,data)
            import warnings
            with warnings.catch_warnings(): warnings.simplefilter('ignore'); z.writestr('checker.py',self.files['checker.py'])
        with self.assertRaises(VerificationError):verify_bundle(path)
        path=self.root/'large.zip';path.write_bytes(b'x'*(MAX_ARCHIVE_BYTES+1))
        with self.assertRaises(VerificationError):verify_bundle(path)

    def test_receipt_and_member_size_and_corrupt_zip_refuse(self):
        files=dict(self.files); files['verification.json']=b'{"format":"one","format":"two"}'
        checksum(files); self.check_refused(files)
        files=dict(self.files); files['README.txt']=b'x'*(2*1024*1024+1)
        checksum(files); self.check_refused(files)
        path=self.root/'truncated.zip';path.write_bytes(b'PK\x03\x04 broken')
        with self.assertRaises(VerificationError): verify_bundle(path)
        process=subprocess.run([sys.executable,'-m','certloom','verify-bundle',str(path)],capture_output=True,text=True)
        self.assertEqual(process.returncode,2);self.assertNotIn('Traceback',process.stderr)

    def test_metadata_rejections(self):
        for kind in ('symlink','directory','encrypted','codec'):
            path=self.root/(kind+'.zip')
            with zipfile.ZipFile(path,'w') as z:
                for name,data in self.files.items():
                    info=zipfile.ZipInfo(name)
                    if name=='checker.py' and kind=='symlink': info.create_system=3;info.external_attr=0o120777<<16
                    if name=='checker.py' and kind=='directory': info.external_attr=0x10
                    z.writestr(info,data)
            if kind in ('encrypted','codec'):
                raw=bytearray(path.read_bytes()); start=0
                while True:
                    pos=raw.find(b'PK\x01\x02',start)
                    if pos<0: break
                    length=int.from_bytes(raw[pos+28:pos+30],'little'); name=raw[pos+46:pos+46+length]
                    if name==b'checker.py':
                        at=pos+(8 if kind=='encrypted' else 10);raw[at:at+2]=(1 if kind=='encrypted' else 99).to_bytes(2,'little');break
                    start=pos+46+length
                path.write_bytes(raw)
            with self.assertRaises(VerificationError, msg=kind):verify_bundle(path)

    def test_atomic_write_failure_competitor_and_symlink(self):
        out=self.root/'output'
        with self.assertRaises(OSError):
            with fresh_output(out) as stream:
                stream.write(b'partial');raise OSError('injected')
        self.assertFalse(out.exists());self.assertFalse(list(self.root.glob('.certloom-*')))
        with self.assertRaises(FileExistsError):
            with fresh_output(out) as stream:
                stream.write(b'ours');out.write_bytes(b'competitor')
        self.assertEqual(out.read_bytes(),b'competitor')
        target=self.root/'target';target.write_bytes(b'original'); link=self.root/'link';link.symlink_to(target)
        with self.assertRaises(FileExistsError):
            with fresh_output(link) as stream: stream.write(b'bad')
        self.assertEqual(target.read_bytes(),b'original')

    def test_two_concurrent_publishers_only_one_wins(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        target=self.root/'race'; gate=Barrier(2)
        def writer(payload):
            try:
                with fresh_output(target) as stream:
                    stream.write(payload); gate.wait(timeout=5)
                return True
            except FileExistsError:
                return False
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes=list(executor.map(writer, (b'first',b'second')))
        self.assertEqual(sorted(outcomes),[False,True])
        self.assertIn(target.read_bytes(),(b'first',b'second'))
        self.assertFalse(list(self.root.glob('.certloom-*')))

    def test_legacy_browser_and_new_browser_zip_actual_js(self):
        files=self.root/'files';files.mkdir()
        for n,b in self.files.items(): (files/n).write_bytes(b)
        js=self.root/'browser.mjs'
        js.write_text('''import fs from "node:fs";\nimport {zipStored,zipWithChecksums} from '''+json.dumps((ROOT/'web/app.mjs').as_uri())+''';\nimport {verifyText} from '''+json.dumps((ROOT/'web/verify.mjs').as_uri())+''';\nconst dir=process.argv[2], names=["checker.py","certificate.json","verification.json","README.txt","LICENSE-FIPY.txt"], files=names.map(name=>({name,bytes:new Uint8Array(fs.readFileSync(dir+"/"+name))}));\nconst certificate=files.find(f=>f.name==="certificate.json").bytes, hex=[...new Uint8Array(await crypto.subtle.digest("SHA-256",certificate))].map(x=>x.toString(16).padStart(2,"0")).join("");\nfiles.find(f=>f.name==="verification.json").bytes=new TextEncoder().encode(JSON.stringify({format:"certloom-verification-v1",certificate_sha256:hex,scope:"Exact stored binary64 linear system; identity is not authenticity.",result:verifyText(new TextDecoder().decode(certificate))}));\nfs.writeFileSync(dir+"/legacy.zip",zipStored(files));fs.writeFileSync(dir+"/new.zip",await zipWithChecksums(files));''')
        subprocess.run(['node',str(js),str(files)],check=True)
        self.assertEqual(verify_bundle(files/'legacy.zip')['checksums'],'absent')
        self.assertEqual(verify_bundle(files/'new.zip')['checksums'],'verified')

if __name__=='__main__':unittest.main()
