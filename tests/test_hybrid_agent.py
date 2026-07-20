import unittest
from unittest.mock import Mock, patch

from bl_reviewer_agent.agent import HybridBLReviewerAgent


class HybridBLReviewerAgentTests(unittest.TestCase):
    def test_skips_llm_for_high_similarity_matches(self):
        llm_agent = Mock()
        agent = HybridBLReviewerAgent(llm_agent=llm_agent, threshold=0.45)

        with patch.object(agent.bi_engine, "calculate_similarity", return_value=0.92):
            result = agent.review({
                "offer_id": "123",
                "title": "BOPP Synthetic Non Tearable Sheets",
                "mcat": "BOPP Synthetic Non Tearable Sheets",
            })

        self.assertEqual(result["flags"], [])
        self.assertIn("High semantic similarity", result["concise_reason"])
        llm_agent.review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
