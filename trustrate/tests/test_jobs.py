"""Job durability and real local fallback checks. Never submit to IBM."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np
from pipeline.models import TrustRateModel
from service.app import jobs,quantum_execution as execution

ROOT=Path(__file__).resolve().parents[1]

class JobTests(unittest.TestCase):
    def test_durable_job_and_invalid_path(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(jobs,"DIRECTORY",Path(directory)):
            jobs.recover()
            receipt=jobs.submit([42],"aer",lambda ids,**kw:[{"backend":"test_fixture","review_id":ids[0]}])
            for _ in range(100):
                stored=jobs.get(receipt["job_id"])
                if stored["status"]=="completed": break
                time.sleep(.01)
            self.assertEqual(stored["status"],"completed")
            self.assertEqual(stored["results"][0]["review_id"],42)
            with self.assertRaises(KeyError): jobs.get("../../.env")

    def test_restart_does_not_resubmit_and_preserves_ibm_id(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(jobs,"DIRECTORY",Path(directory)):
            original={"job_id":"job_"+"a"*32,"status":"running","ibm_job_id":"test-retained-receipt"}
            jobs.write(original); jobs.recover()
            restored=jobs.get(original["job_id"])
            self.assertEqual(restored["status"],"interrupted")
            self.assertEqual(restored["ibm_job_id"],original["ibm_job_id"])

    def test_missing_noise_uses_honestly_labeled_ideal_aer(self):
        model=TrustRateModel.load(ROOT/"service/artifacts/model.joblib")
        with patch.object(execution,"hardware_kernel",side_effect=RuntimeError("test unavailable")),patch.object(execution,"noise_kernel",side_effect=RuntimeError("test no cache")):
            values,info=execution.quantum_raw(model,np.zeros((1,10)),"ibm_with_fallback")
            self.assertTrue(np.isfinite(values).all())
            self.assertEqual(info["backend"],"aer_simulator")
            self.assertIn("ideal Aer",info["fallback_reason"])
            self.assertIsNone(info["ibm_job_id"])

    @unittest.skipUnless(execution.CACHE.exists(),"Requires locally cached real device noise")
    def test_real_noise_fallback_and_strict_ibm_failure(self):
        model=TrustRateModel.load(ROOT/"service/artifacts/model.joblib")
        with patch.object(execution,"hardware_kernel",side_effect=RuntimeError("test unavailable")):
            values,info=execution.quantum_raw(model,np.zeros((1,10)),"ibm_with_fallback")
            self.assertTrue(np.isfinite(values).all())
            self.assertTrue(info["backend"].startswith("aer_noise_ibm_"))
            self.assertIsNone(info["ibm_job_id"])
            with self.assertRaises(RuntimeError): execution.quantum_raw(model,np.zeros((1,10)),"ibm")

if __name__=="__main__": unittest.main()
