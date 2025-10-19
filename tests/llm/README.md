# Vertex AI Integration Tests

This directory contains integration tests that make actual calls to the Vertex AI API to verify our LLM integration works correctly with real models.

## Prerequisites

Before running these tests, you need:

1. **GCP Credentials**: Authenticate with Google Cloud
   ```bash
   gcloud auth application-default login
   ```

2. **Environment Variables**:
   ```bash
   export GCP_PROJECT="your-project-id"
   export GCP_LOCATION="us-central1"  # Optional, defaults to us-central1
   ```

3. **Vertex AI API Enabled**: Ensure the Vertex AI API is enabled in your GCP project
   ```bash
   gcloud services enable aiplatform.googleapis.com --project=your-project-id
   ```

4. **Model Access**: Ensure you have access to the models being tested:
   - Gemini: `gemini-2.0-flash-exp`
   - Claude: `claude-3-5-sonnet-v2@20241022` (requires Anthropic on Vertex AI)

## Running the Tests

### Run all integration tests
```bash
pytest tests/llm/test_integration.py -v -s
```

The `-s` flag shows print output from the tests, which includes the actual LLM responses.

### Run specific test classes
```bash
# Test only Gemini integration
pytest tests/llm/test_integration.py::TestGeminiIntegration -v -s

# Test only Claude integration
pytest tests/llm/test_integration.py::TestClaudeIntegration -v -s

# Test cross-model compatibility
pytest tests/llm/test_integration.py::TestCrossModelCompatibility -v -s
```

### Run specific tests
```bash
# Test Gemini text generation
pytest tests/llm/test_integration.py::TestGeminiIntegration::test_gemini_simple_text_generation -v -s

# Test Claude function calling
pytest tests/llm/test_integration.py::TestClaudeIntegration::test_claude_function_calling -v -s
```

### Skip integration tests (default test run)
```bash
# Run all tests EXCEPT integration tests
pytest -m "not integration"
```

## What the Tests Verify

### Gemini Tests (`TestGeminiIntegration`)
- **test_gemini_simple_text_generation**: Basic text generation with Gemini
- **test_gemini_with_system_prompt**: System prompt handling
- **test_gemini_function_calling**: Tool/function calling capability

### Claude Tests (`TestClaudeIntegration`)
- **test_claude_simple_text_generation**: Basic text generation with Claude
- **test_claude_with_system_prompt**: System prompt handling
- **test_claude_function_calling**: Tool/function calling capability

### Cross-Model Tests (`TestCrossModelCompatibility`)
- **test_same_code_works_for_both_models**: Verifies our code works identically with both Gemini and Claude

## Expected Behavior

Each test:
1. Creates a Vertex AI client with the appropriate model configuration
2. Formats messages using our `format_messages()` function
3. Calls `call_llm()` to invoke the Vertex AI API
4. Verifies the response structure (text, tool_calls, token_usage, model_name)
5. Prints the actual responses for manual inspection

## Skipping Tests

If you don't have GCP credentials configured, the tests will automatically skip with a message:
```
SKIPPED [1] tests/llm/test_integration.py:42: GCP_PROJECT environment variable not set
```

## Cost Considerations

These tests make real API calls and will incur small costs:
- Gemini 2.0 Flash: Very low cost (typically < $0.01 per test run)
- Claude 3.5 Sonnet: Low cost (typically < $0.05 per test run)

Total cost for a full test run is typically < $0.10.

## Troubleshooting

### Authentication Errors
```
google.auth.exceptions.DefaultCredentialsError
```
**Solution**: Run `gcloud auth application-default login`

### Model Not Found
```
404 Not Found: Model not found
```
**Solution**:
- For Gemini: Verify the model name is correct and available in your region
- For Claude: Ensure you have access to Anthropic models on Vertex AI

### Permission Denied
```
403 Forbidden: Permission denied
```
**Solution**: Ensure your GCP account has the necessary IAM permissions:
- `roles/aiplatform.user` or `roles/aiplatform.admin`

### Project Not Set
```
SKIPPED: GCP_PROJECT environment variable not set
```
**Solution**: Set the environment variable:
```bash
export GCP_PROJECT="your-project-id"
```
