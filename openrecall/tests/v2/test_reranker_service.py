
import pytest
from unittest.mock import MagicMock, patch
import requests
from openrecall.server.services.reranker import APIReranker, LocalReranker, get_reranker
from openrecall.shared.config import Settings

class TestAPIReranker:
    def test_init(self, mock_settings):
        with patch('openrecall.server.services.reranker.settings', mock_settings):
            reranker = APIReranker()
            assert reranker.api_url == mock_settings.reranker_url

    def test_compute_score_success(self, mock_settings):
        with patch('openrecall.server.services.reranker.settings', mock_settings):
            reranker = APIReranker()
            
            with patch('requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.json.return_value = [0.9, 0.1, 0.5]
                mock_response.raise_for_status.return_value = None
                mock_post.return_value = mock_response
                
                query = "test query"
                docs = ["doc1", "doc2", "doc3"]
                scores = reranker.compute_score(query, docs)
                
                assert scores == [0.9, 0.1, 0.5]
                mock_post.assert_called_once()
                args, kwargs = mock_post.call_args
                assert kwargs['json']['query'] == query
                assert kwargs['json']['documents'] == docs
                assert kwargs['json']['model'] == mock_settings.reranker_model

    def test_compute_score_dict_response(self, mock_settings):
         with patch('openrecall.server.services.reranker.settings', mock_settings):
            reranker = APIReranker()
            
            with patch('requests.post') as mock_post:
                mock_response = MagicMock()
                mock_response.json.return_value = {"scores": [0.8, 0.2]}
                mock_post.return_value = mock_response
                
                scores = reranker.compute_score("q", ["d1", "d2"])
                assert scores == [0.8, 0.2]

    def test_compute_score_failure(self, mock_settings):
        with patch('openrecall.server.services.reranker.settings', mock_settings):
            reranker = APIReranker()
            
            with patch('requests.post') as mock_post:
                mock_post.side_effect = requests.RequestException("API Error")
                
                docs = ["doc1", "doc2"]
                scores = reranker.compute_score("query", docs)
                
                # Should return zeros and log error (not crashing)
                assert scores == [0.0, 0.0]

    def test_compute_score_empty(self, mock_settings):
        with patch('openrecall.server.services.reranker.settings', mock_settings):
            reranker = APIReranker()
            scores = reranker.compute_score("query", [])
            assert scores == []

class TestLocalReranker:
    def test_lazy_loading(self, mock_settings):
        with patch('openrecall.server.services.reranker.settings', mock_settings):
            reranker = LocalReranker()
            assert reranker.model is None
            assert reranker.tokenizer is None

    @patch('transformers.AutoTokenizer')
    @patch('transformers.AutoModelForSequenceClassification')
    def test_load_model_on_compute(self, mock_model_cls, mock_tokenizer_cls, mock_settings):
        # Setup mocks
        mock_tokenizer = MagicMock()
        
        # Create a mock object that behaves like BatchEncoding (dict + .to method)
        class MockBatchEncoding(dict):
            def to(self, device):
                return self
        
        mock_inputs = MockBatchEncoding({'input_ids': MagicMock(), 'attention_mask': MagicMock()})
        mock_tokenizer.return_value = mock_inputs
        
        mock_tokenizer_cls.from_pretrained.return_value = mock_tokenizer
        
        mock_model = MagicMock()
        mock_model.eval.return_value = None
        mock_model.to.return_value = mock_model # Ensure .to() returns the mock itself
        
        # Mocking the output of model(**inputs)
        mock_output = MagicMock()
        mock_model.return_value = mock_output
        mock_model_cls.from_pretrained.return_value = mock_model

        with patch('openrecall.server.services.reranker.settings', mock_settings):
            reranker = LocalReranker()
            
            # First call should trigger load
            scores = reranker.compute_score("query", ["doc1"])
            
            assert reranker.model is not None
            assert reranker.tokenizer is not None
            
            # Verify model was called
            mock_model.assert_called()
            # Verify we didn't hit the exception path (which returns [0.0])
            # If it returned a Mock (which is truthy), it means it passed the try block
            assert scores != [0.0]
            
            mock_model_cls.from_pretrained.assert_called_once()
            mock_tokenizer_cls.from_pretrained.assert_called_once()

    @patch('transformers.AutoTokenizer')
    @patch('transformers.AutoModelForSequenceClassification')
    def test_compute_score_error(self, mock_model_cls, mock_tokenizer_cls, mock_settings):
        mock_model_cls.from_pretrained.side_effect = Exception("Model load failed")
        
        with patch('openrecall.server.services.reranker.settings', mock_settings):
            reranker = LocalReranker()
            scores = reranker.compute_score("query", ["doc1"])
            
            # Should fail gracefully returning zeros
            assert scores == [0.0]

def test_get_reranker_factory(mock_settings):
    # Test default (api)
    with patch('openrecall.server.services.reranker.settings', mock_settings):
        mock_settings.reranker_mode = "api"
        reranker = get_reranker()
        assert isinstance(reranker, APIReranker)
        
    # Test local
    with patch('openrecall.server.services.reranker.settings', mock_settings):
        mock_settings.reranker_mode = "local"
        reranker = get_reranker()
        assert isinstance(reranker, LocalReranker)
