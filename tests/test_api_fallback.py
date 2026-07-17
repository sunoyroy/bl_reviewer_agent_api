import unittest

from bl_reviewer_agent import api


class ApiFallbackTests(unittest.TestCase):
    def test_review_single_falls_back_without_llm_key(self):
        body = api.ReviewRequest(
            offer_id="123",
            title="BOPP Synthetic Non Tearable Sheets",
            mcat="Non Tearable Paper",
            isq_filled={"Printing Compatibility": "Offset"},
            isq_asked=["Printing Compatibility"],
        )

        result = api.review_single(body)

        self.assertIsInstance(result.flags, list)
        self.assertTrue(isinstance(result.concise_reason, str) and result.concise_reason)


if __name__ == "__main__":
    unittest.main()
