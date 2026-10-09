"""Verify saved evidence without spending hardware quota or reading credentials."""
import hashlib
import json
from pathlib import Path
import unittest
import numpy as np

ARTIFACTS=Path(__file__).resolve().parents[1]/"service/artifacts"

@unittest.skipUnless((ARTIFACTS/"hardware-kernel.npy").exists(),"Requires a collected IBM experiment")
class HardwareEvidenceTests(unittest.TestCase):
    def test_real_kernel_receipt_and_matrix(self):
        receipt=json.loads((ARTIFACTS/"hardware.json").read_text())
        self.assertEqual(receipt["status"],"DONE")
        self.assertTrue(receipt["result_verified"])
        self.assertTrue(receipt["ibm_job_id"] and not receipt["ibm_job_id"].startswith("demo-"))
        self.assertTrue(receipt["backend"].startswith("ibm_"))
        plan=json.loads((ARTIFACTS/"hardware-plan.json").read_text())
        self.assertEqual(hashlib.sha256((ARTIFACTS/"hardware-plan.json").read_bytes()).hexdigest(),receipt["plan_sha256"])
        kernel=np.load(ARTIFACTS/"hardware-kernel.npy",allow_pickle=False)
        n=receipt["n_train"]+receipt["n_test"]
        self.assertEqual(kernel.shape,(n,n))
        self.assertEqual(len(plan["pairs"]),receipt["circuits"])
        self.assertEqual(receipt["circuits"],n*(n-1)//2)
        self.assertTrue(np.isfinite(kernel).all())
        self.assertTrue(((kernel>=0)&(kernel<=1)).all())
        np.testing.assert_allclose(kernel,kernel.T)
        np.testing.assert_allclose(np.diag(kernel),1)
        aer=np.load(ARTIFACTS/"hardware-aer-kernel.npy",allow_pickle=False)
        self.assertAlmostEqual(float(np.mean(np.abs(kernel-aer))),receipt["kernel_mean_absolute_difference"])
        self.assertEqual(len(receipt["results"]),receipt["n_test"])
        self.assertTrue(all(np.isfinite(r["hardware_anomaly_raw"]) for r in receipt["results"]))

if __name__=="__main__": unittest.main()
