# API Contract Baseline

## GET /v1/models

**Response**: `200 OK`
```json
{
  "object": "list",
  "data": [
    {"id": "free-proxy/auto", "object": "model", "owned_by": "free-proxy"}
  ]
}
```

## POST /v1/chat/completions (non-stream)

**Request**: `{"model": "free-proxy/auto", "messages": [{"role": "user", "content": "hello"}]}`

**Response**: `200 OK`, `Content-Type: application/json; charset=utf-8`
```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "model": "provider/model",
  "choices": [{"index": 0, "message": {"role": "assistant", "content": "..."}, "finish_reason": "stop"}],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

## POST /v1/chat/completions (stream)

**Request**: `{"model": "free-proxy/auto", "messages": [...], "stream": true}`

**Response**: `200 OK`, `Content-Type: text/event-stream; charset=utf-8`
```
data: {"id":"...","object":"chat.completion.chunk","model":"...","choices":[{"index":0,"delta":{"content":"..."},"finish_reason":null}]}

data: {"id":"...","object":"chat.completion.chunk","model":"...","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## Error Responses

**400 Bad Request** (missing model):
```json
{"error": {"message": "missing model", "type": "invalid_request_error", "param": null, "code": null}}
```

**400 Bad Request** (deprecated model):
```json
{"error": {"message": "...", "type": "invalid_request_error", "param": null, "code": "model_deprecated"}}
```

## POST /chat/completions (UI debug)

**Request**: `{"provider": "longcat", "model": "LongCat-Flash", "messages": [...]}`

**Response (non-stream)**: `200 OK`
```json
{"ok": true, "provider": "longcat", "model": "LongCat-Flash", "actual_model": "LongCat-Flash", "content": "..."}
```

**Response (stream)**: `200 OK`, `Content-Type: text/event-stream`
```
data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":"..."},"index":0}]}

data: [DONE]
```
