# Security Vulnerability Audit - PyTagManager

**Audit Date:** 2026-10-27
**Repository:** /Users/georgimullassery/Desktop/Projects/PyTagManager
**Total Findings:** 326

## Summary
- **Critical:** 296
- **Medium:** 30

## Findings

### 1. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/_code/code.py:164
- **Description:** eval()
- **Evidence (Line):** `def eval(self, code, **vars):`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 2. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/_code/code.py:173
- **Description:** eval()
- **Evidence (Line):** `return eval(code, self.f_globals, f_locals)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 3. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/_code/code.py:326
- **Description:** eval()
- **Evidence (Line):** `# however via `exec(...)` / `eval(...)` they can be other types`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 4. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/_code/code.py:326
- **Description:** exec()
- **Evidence (Line):** `# however via `exec(...)` / `eval(...)` they can be other types`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 5. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/_py/path.py:1153
- **Description:** exec()
- **Evidence (Line):** `exec(f.read(), mod.__dict__)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 6. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/_py/path.py:1159
- **Description:** exec()
- **Evidence (Line):** `def sysexec(self, *argv: os.PathLike[str], **popen_opts: Any) -> str:`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 7. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/assertion/rewrite.py:188
- **Description:** exec()
- **Evidence (Line):** `exec(co, module.__dict__)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 8. [Critical] Insecure Deserialization
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/assertion/rewrite.py:393
- **Description:** marshal load
- **Evidence (Line):** `co = marshal.load(fp)`
- **Exploit Scenario:** Attacker could achieve remote code execution
- **Fix Recommendation:** Use safe serialization formats (JSON), avoid pickle/yaml.load with untrusted data
- **Confidence:** High

### 9. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/capture.py:1112
- **Description:** os.system()
- **Evidence (Line):** `os.system('echo "hello"')`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 10. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/capture.py:1140
- **Description:** os.system()
- **Evidence (Line):** `os.system('echo "hello"')`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 11. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/mark/__init__.py:66
- **Description:** eval()
- **Evidence (Line):** `def test_eval(test_input, expected):`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 12. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/mark/__init__.py:67
- **Description:** eval()
- **Evidence (Line):** `assert eval(test_input) == expected`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 13. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/mark/expression.py:295
- **Description:** eval()
- **Evidence (Line):** `"""Adapts a matcher function to a locals mapping as required by eval()."""`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 14. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/mark/expression.py:353
- **Description:** eval()
- **Evidence (Line):** `return bool(eval(self._code, {"__builtins__": {}}, MatcherAdapter(matcher)))`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 15. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/pytester.py:296
- **Description:** eval()
- **Evidence (Line):** `if eval(check, backlocals, call.__dict__):`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 16. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/skipping.py:92
- **Description:** eval()
- **Evidence (Line):** `If an old-style string condition is given, it is eval()'d, otherwise the`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 17. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/_pytest/skipping.py:119
- **Description:** eval()
- **Evidence (Line):** `result = eval(condition_code, globals_)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 18. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/cffi/_cffi_gen_src.py:53
- **Description:** exec()
- **Evidence (Line):** `exec(compiled, globs, globs)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 19. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/cffi/recompiler.py:80
- **Description:** eval()
- **Evidence (Line):** `flags = eval(self.flags, G_FLAGS)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 20. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/cffi/setuptools_ext.py:26
- **Description:** exec()
- **Evidence (Line):** `exec(code, glob, glob)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 21. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/coverage/execfile.py:218
- **Description:** exec()
- **Evidence (Line):** `exec(code, main_mod.__dict__)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 22. [Critical] Insecure Deserialization
- **File:** .venv-test/lib/python3.12/site-packages/coverage/execfile.py:331
- **Description:** marshal load
- **Evidence (Line):** `code = marshal.load(fpyc)`
- **Exploit Scenario:** Attacker could achieve remote code execution
- **Fix Recommendation:** Use safe serialization formats (JSON), avoid pickle/yaml.load with untrusted data
- **Confidence:** High

### 23. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/coverage/htmlfiles/coverage_html.js:274
- **Description:** exec()
- **Evidence (Line):** `const match = /\.([0-9]+)/.exec(cell.textContent);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 24. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/coverage/parser.py:673
- **Description:** eval()
- **Evidence (Line):** `return True, eval(node.id)  # pylint: disable=eval-used`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 25. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/coverage/templite.py:72
- **Description:** exec()
- **Evidence (Line):** `exec(python_source, global_namespace)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 26. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/cryptography/hazmat/_oid.py:372
- **Description:** Password Assignment detected
- **Evidence (Line):** `AttributeOID.CHALLENGE_PASSWORD: "challengePassword",`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 27. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/cryptography/hazmat/primitives/serialization/ssh.py:77
- **Description:** Private Key detected
- **Evidence (Line):** `_SK_START = b"-----BEGIN OPENSSH PRIVATE KEY-----"`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 28. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/google/auth/crypt/_python_rsa.py:38
- **Description:** Private Key detected
- **Evidence (Line):** `_PKCS1_MARKER = ("-----BEGIN RSA PRIVATE KEY-----", "-----END RSA PRIVATE KEY-----")`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 29. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/google/auth/crypt/_python_rsa.py:39
- **Description:** Private Key (PKCS8) detected
- **Evidence (Line):** `_PKCS8_MARKER = ("-----BEGIN PRIVATE KEY-----", "-----END PRIVATE KEY-----")`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 30. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/google/auth/environment_vars.py:131
- **Description:** Token Assignment detected
- **Evidence (Line):** `GOOGLE_API_ENABLE_RUNTIME_BOUND_TOKEN = "GOOGLE_API_ENABLE_RUNTIME_BOUND_TOKEN"`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 31. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/google/auth/transport/_mtls_helper.py:43
- **Description:** Private Key detected
- **Evidence (Line):** `# "-----BEGIN EC PRIVATE KEY-----...",`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 32. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/google/auth/transport/_mtls_helper.py:44
- **Description:** Private Key detected
- **Evidence (Line):** `# "-----BEGIN RSA PRIVATE KEY-----..."`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 33. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/google/auth/transport/_mtls_helper.py:42
- **Description:** Private Key (PKCS8) detected
- **Evidence (Line):** `# "-----BEGIN PRIVATE KEY-----...",`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 34. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/google/oauth2/challenges.py:98
- **Description:** Password Assignment detected
- **Evidence (Line):** `passwd = get_user_password("Please enter your password:")`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 35. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/google/oauth2/gdch_credentials.py:44
- **Description:** Private Key detected
- **Evidence (Line):** `"private_key": "-----BEGIN EC PRIVATE KEY-----\n<key bytes>\n-----END EC PRIVATE KEY-----\n",`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 36. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/googleapiclient/discovery_cache/documents/appengine.v1.json:3140
- **Description:** Private Key detected
- **Evidence (Line):** `"description": "Unencrypted PEM encoded RSA private key. This field is set once on certificate creat`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 37. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/googleapiclient/discovery_cache/documents/appengine.v1alpha.json:1584
- **Description:** Private Key detected
- **Evidence (Line):** `"description": "Unencrypted PEM encoded RSA private key. This field is set once on certificate creat`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 38. [Critical] Hardcoded Secret
- **File:** .venv-test/lib/python3.12/site-packages/googleapiclient/discovery_cache/documents/appengine.v1beta.json:3369
- **Description:** Private Key detected
- **Evidence (Line):** `"description": "Unencrypted PEM encoded RSA private key. This field is set once on certificate creat`
- **Exploit Scenario:** Attacker could extract credentials and gain unauthorized access
- **Fix Recommendation:** Move secrets to environment variables or secret manager, rotate compromised credentials
- **Confidence:** High

### 39. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/greenlet/tests/test_version.py:36
- **Description:** os.popen()
- **Evidence (Line):** `with os.popen(invoke_setup) as f:`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 40. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/packaging/_parser.py:397
- **Description:** eval()
- **Evidence (Line):** `value = ast.literal_eval(python_str)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 41. [Critical] Insecure Deserialization
- **File:** .venv-test/lib/python3.12/site-packages/packaging/_structures.py:10
- **Description:** pickle load/dumps
- **Evidence (Line):** `stand-in classes so that ``pickle.loads()`` can resolve those references.`
- **Exploit Scenario:** Attacker could achieve remote code execution
- **Fix Recommendation:** Use safe serialization formats (JSON), avoid pickle/yaml.load with untrusted data
- **Confidence:** High

### 42. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/_impl/_transport.py:120
- **Description:** exec()
- **Evidence (Line):** `self._proc = await asyncio.create_subprocess_exec(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 43. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 44. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 45. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 46. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 47. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 48. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 49. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 50. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 51. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 52. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 53. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 54. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 55. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 56. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 57. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 58. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 59. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 60. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 61. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 62. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 63. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 64. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 65. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 66. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/api.json:1
- **Description:** eval()
- **Evidence (Line):** `[{"name":"APIRequest","spec":[{"type":"text","text":"Exposes API that can be used for the Web API te`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 67. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:12646
- **Description:** eval()
- **Evidence (Line):** `source = '\nvar __commonJS = obj => {\n  let required = false;\n  let result;\n  return function __r`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 68. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:15584
- **Description:** eval()
- **Evidence (Line):** `source2 = '\nvar __commonJS = obj => {\n  let required = false;\n  let result;\n  return function __`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 69. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:15901
- **Description:** eval()
- **Evidence (Line):** `source3 = '\nvar __commonJS = obj => {\n  let required = false;\n  let result;\n  return function __`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 70. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:15901
- **Description:** eval()
- **Evidence (Line):** `source3 = '\nvar __commonJS = obj => {\n  let required = false;\n  let result;\n  return function __`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 71. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:15901
- **Description:** eval()
- **Evidence (Line):** `source3 = '\nvar __commonJS = obj => {\n  let required = false;\n  let result;\n  return function __`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 72. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:15901
- **Description:** eval()
- **Evidence (Line):** `source3 = '\nvar __commonJS = obj => {\n  let required = false;\n  let result;\n  return function __`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 73. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:15901
- **Description:** eval()
- **Evidence (Line):** `source3 = '\nvar __commonJS = obj => {\n  let required = false;\n  let result;\n  return function __`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 74. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:18372
- **Description:** eval()
- **Evidence (Line):** `let result3 = evaledExpression ?? globalThis.eval(expression3);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 75. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:18486
- **Description:** eval()
- **Evidence (Line):** `const callback = injected.eval(callbackText2);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 76. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:53602
- **Description:** eval()
- **Evidence (Line):** `return await this._frame.$$eval(this._selector, pageFunction, arg);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 77. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:53787
- **Description:** eval()
- **Evidence (Line):** `return await this._frame.$$eval(this._selector, (ee) => ee.map((e) => e.innerText));`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 78. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:53790
- **Description:** eval()
- **Evidence (Line):** `return await this._frame.$$eval(this._selector, (ee) => ee.map((e) => e.textContent || ""));`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 79. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:55577
- **Description:** eval()
- **Evidence (Line):** `async $eval(selector, pageFunction, arg) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 80. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:55582
- **Description:** eval()
- **Evidence (Line):** `async $$eval(selector, pageFunction, arg) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 81. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:56061
- **Description:** eval()
- **Evidence (Line):** `async $eval(selector, pageFunction, arg) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 82. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:56065
- **Description:** eval()
- **Evidence (Line):** `async $$eval(selector, pageFunction, arg) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 83. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:56582
- **Description:** eval()
- **Evidence (Line):** `async $eval(selector, pageFunction, arg) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 84. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:56584
- **Description:** eval()
- **Evidence (Line):** `return await this._mainFrame.$eval(selector, pageFunction, arg);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 85. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:56586
- **Description:** eval()
- **Evidence (Line):** `async $$eval(selector, pageFunction, arg) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 86. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:56588
- **Description:** eval()
- **Evidence (Line):** `return await this._mainFrame.$$eval(selector, pageFunction, arg);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 87. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:61089
- **Description:** eval()
- **Evidence (Line):** `const value = eval(`(${expr})`);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 88. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:61096
- **Description:** eval()
- **Evidence (Line):** `const value = eval(`(${expr})`);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 89. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/coreBundle.js:27655
- **Description:** exec()
- **Evidence (Line):** `const match = /^Inst (\S+) /.exec(line);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 90. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/serverRegistry.js:1103
- **Description:** exec()
- **Evidence (Line):** `const match = /^\\+/.exec(remaining());`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 91. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/serverRegistry.js:1394
- **Description:** exec()
- **Evidence (Line):** `const match = REGEX_NON_SPECIAL_CHARS.exec(remaining());`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 92. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/serverRegistry.js:1608
- **Description:** exec()
- **Evidence (Line):** `const match = /^(.*?)\.(\w+)$/.exec(str);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 93. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/serverRegistry.js:1709
- **Description:** exec()
- **Evidence (Line):** `match = regex.exec(output);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 94. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/serverRegistry.js:3076
- **Description:** exec()
- **Evidence (Line):** `const match = /^\\+/.exec(remaining());`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 95. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/serverRegistry.js:3367
- **Description:** exec()
- **Evidence (Line):** `const match = REGEX_NON_SPECIAL_CHARS.exec(remaining());`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 96. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/serverRegistry.js:3581
- **Description:** exec()
- **Evidence (Line):** `const match = /^(.*?)\.(\w+)$/.exec(str);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 97. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/serverRegistry.js:3682
- **Description:** exec()
- **Evidence (Line):** `match = regex.exec(output);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 98. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/serverRegistry.js:3851
- **Description:** exec()
- **Evidence (Line):** `while (match = /(\\).|([@?!+*]\(.*\))/g.exec(str)) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 99. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:720
- **Description:** exec()
- **Evidence (Line):** `var match = /^(-?(?:\d+)?\.?\d+) *(milliseconds?|msecs?|ms|seconds?|secs?|s|minutes?|mins?|m|hours?|`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 100. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:1764
- **Description:** exec()
- **Evidence (Line):** `while ((match = LINE.exec(lines)) != null) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 101. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:5744
- **Description:** exec()
- **Evidence (Line):** `const configMountPoint = /(?<!#.*)root\s*=\s*(?<mountPoint>.*)/g.exec(configContent);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 102. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:9775
- **Description:** exec()
- **Evidence (Line):** `const m = regex.exec(val);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 103. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:12962
- **Description:** exec()
- **Evidence (Line):** `const subnet = constants.RE_SUBNET_STRING.exec(address);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 104. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:13666
- **Description:** exec()
- **Evidence (Line):** `const subnet = constants6.RE_SUBNET_STRING.exec(address);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 105. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:13678
- **Description:** exec()
- **Evidence (Line):** `const zone = constants6.RE_ZONE_STRING.exec(address);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 106. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:13737
- **Description:** exec()
- **Evidence (Line):** `result = constants6.RE_URL_WITH_PORT.exec(url2);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 107. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:13749
- **Description:** exec()
- **Evidence (Line):** `result = constants6.RE_URL.exec(url2);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 108. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:23953
- **Description:** exec()
- **Evidence (Line):** `let match = first.exec(source);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 109. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:23960
- **Description:** exec()
- **Evidence (Line):** `while (match = line.exec(source)) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 110. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:23974
- **Description:** exec()
- **Evidence (Line):** `match = last.exec(source);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 111. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:29599
- **Description:** exec()
- **Evidence (Line):** `var match = /^\w+:\/\/[^\/]*/.exec(dir);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 112. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:29626
- **Description:** exec()
- **Evidence (Line):** `while (match = re.exec(fileData)) lastMatch = match;`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 113. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:29689
- **Description:** exec()
- **Evidence (Line):** `var match = /^eval at ([^(]+) \((.+):(\d+):(\d+)\)$/.exec(origin);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 114. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:29698
- **Description:** exec()
- **Evidence (Line):** `match = /^eval at ([^(]+) \((.+)\)$/.exec(origin);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 115. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:29848
- **Description:** exec()
- **Evidence (Line):** `var match = /\n    at [^(]+ \((.*):(\d+):(\d+)\)/.exec(error48.stack);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 116. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:30643
- **Description:** exec()
- **Evidence (Line):** `} else if (parts = metaKeyCodeRe.exec(s)) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 117. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:30646
- **Description:** exec()
- **Evidence (Line):** `} else if (parts = fnKeyRe.exec(s)) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 118. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:35481
- **Description:** exec()
- **Evidence (Line):** `const match = /^\\+/.exec(remaining());`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 119. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:35772
- **Description:** exec()
- **Evidence (Line):** `const match = REGEX_NON_SPECIAL_CHARS.exec(remaining());`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 120. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:35986
- **Description:** exec()
- **Evidence (Line):** `const match = /^(.*?)\.(\w+)$/.exec(str);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 121. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:36087
- **Description:** exec()
- **Evidence (Line):** `match = regex.exec(output);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 122. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:37454
- **Description:** exec()
- **Evidence (Line):** `const match = /^\\+/.exec(remaining());`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 123. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:37745
- **Description:** exec()
- **Evidence (Line):** `const match = REGEX_NON_SPECIAL_CHARS.exec(remaining());`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 124. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:37959
- **Description:** exec()
- **Evidence (Line):** `const match = /^(.*?)\.(\w+)$/.exec(str);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 125. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:38060
- **Description:** exec()
- **Evidence (Line):** `match = regex.exec(output);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 126. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:38229
- **Description:** exec()
- **Evidence (Line):** `while (match = /(\\).|([@?!+*]\(.*\))/g.exec(str)) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 127. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:46642
- **Description:** exec()
- **Evidence (Line):** `const matches = RELATIVE_JSON_POINTER.exec($data);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 128. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:50411
- **Description:** exec()
- **Evidence (Line):** `const matches = DATE.exec(str);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 129. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:50431
- **Description:** exec()
- **Evidence (Line):** `const matches = TIME.exec(str);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 130. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:50462
- **Description:** exec()
- **Evidence (Line):** `const a1 = TIME.exec(t1);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 131. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:50463
- **Description:** exec()
- **Evidence (Line):** `const a2 = TIME.exec(t2);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 132. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:53262
- **Description:** exec()
- **Evidence (Line):** `const matches = RELATIVE_JSON_POINTER.exec($data);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 133. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:56416
- **Description:** exec()
- **Evidence (Line):** `var results = parseRegExp.exec(val);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 134. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:56488
- **Description:** exec()
- **Evidence (Line):** `while (match = PARAM_REGEXP.exec(header)) {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 135. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:57210
- **Description:** exec()
- **Evidence (Line):** `(function exec() {`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 136. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:57216
- **Description:** exec()
- **Evidence (Line):** `exec();`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 137. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:57858
- **Description:** exec()
- **Evidence (Line):** `const headerMatch = /^(?:Index:|diff(?: -r \w+)+)\s+/.exec(line);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 138. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/utilsBundle.js:57881
- **Description:** exec()
- **Evidence (Line):** `const fileHeaderMatch = /^(---|\+\+\+)\s+/.exec(diffstr[i]);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 139. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/htmlReport/report.js:49
- **Description:** exec()
- **Evidence (Line):** ``).replace(Xg,"")}function Ld(t,e){return e=Yd(e),Yd(t)===e}function wt(t,e,n,l,a,s){switch(n){case"`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 140. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/htmlReport/report.js:56
- **Description:** exec()
- **Evidence (Line):** `rgb(0 0 0 / 25%) 0px 6px 12px`},Vh=({diff:i,noTargetBlank:u,hideDetails:c})=>{const[f,r]=it.useState`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 141. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:1
- **Description:** exec()
- **Evidence (Line):** `import{g as Ju}from"./index-DA10QRaq.js";var vi={exports:{}},Zu=vi.exports,pa;function mt(){return p`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 142. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:1
- **Description:** exec()
- **Evidence (Line):** `import{g as Ju}from"./index-DA10QRaq.js";var vi={exports:{}},Zu=vi.exports,pa;function mt(){return p`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 143. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:1
- **Description:** exec()
- **Evidence (Line):** `import{g as Ju}from"./index-DA10QRaq.js";var vi={exports:{}},Zu=vi.exports,pa;function mt(){return p`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 144. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:1
- **Description:** exec()
- **Evidence (Line):** `import{g as Ju}from"./index-DA10QRaq.js";var vi={exports:{}},Zu=vi.exports,pa;function mt(){return p`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 145. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:4
- **Description:** exec()
- **Evidence (Line):** ``,t);i==-1&&(i=e.length);var o=e.slice(t,e.charAt(i-1)=="\r"?i-1:i),l=o.indexOf("\r");l!=-1?(n.push(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 146. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 147. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 148. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 149. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 150. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 151. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 152. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 153. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:25
- **Description:** exec()
- **Evidence (Line):** ``;O.replaceSelection(q+q,null),S(O,-1),N=O.listSelections();for(var p=0;p<N.length;p++){var W=N[p].h`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 154. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:26
- **Description:** exec()
- **Evidence (Line):** ``+J}X=X*2,M.lastIndex=N.ch;var P=M.exec(z);if(P){var V=z.slice(0,P.index).split(``
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 155. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:28
- **Description:** exec()
- **Evidence (Line):** ``),G=N.line+V.length-1,c=V[V.length-1].length;return{from:pe(G,c),to:pe(G+F.length-1,F.length==1?c+F`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 156. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:31
- **Description:** exec()
- **Evidence (Line):** ``),c=p+F.length,T=F[F.length-1].length;return{from:pe(c,T),to:pe(c+G.length-1,G.length==1?T+G[0].len`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 157. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:32
- **Description:** exec()
- **Evidence (Line):** ``:J=="r"?"\r":J=="t"?"	":J=="\\"?"\\":W})}function S(p){var W=p.match(/^\/(.*)\/([a-z]*)$/);if(W)try`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 158. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:32
- **Description:** exec()
- **Evidence (Line):** ``:J=="r"?"\r":J=="t"?"	":J=="\\"?"\\":W})}function S(p){var W=p.match(/^\/(.*)\/([a-z]*)$/);if(W)try`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 159. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/codeMirrorModule-BHYmBp6h.js:32
- **Description:** exec()
- **Evidence (Line):** ``:J=="r"?"\r":J=="t"?"	":J=="\\"?"\\":W})}function S(p){var W=p.match(/^\/(.*)\/([a-z]*)$/);if(W)try`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 160. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/index-DA10QRaq.js:50
- **Description:** exec()
- **Evidence (Line):** ``).replace(Y0,"")}function ym(e,t){return t=pm(t),pm(e)===t}function Ce(e,t,n,i,r,f){switch(n){case"`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 161. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/index-DA10QRaq.js:136
- **Description:** exec()
- **Evidence (Line):** ``,"sy")}catch{l=/(.*?)[ \t]*\r?\n/sy,a=/[ \t]*(.*?)[ \t]*\r?\n/sy}let s=l.exec(u);if(!s)return u;let`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 162. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/index-DA10QRaq.js:136
- **Description:** exec()
- **Evidence (Line):** ``,"sy")}catch{l=/(.*?)[ \t]*\r?\n/sy,a=/[ \t]*(.*?)[ \t]*\r?\n/sy}let s=l.exec(u);if(!s)return u;let`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 163. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/recorder/assets/index-DA10QRaq.js:138
- **Description:** exec()
- **Evidence (Line):** ``:(c+=o+s[1],o=" "),h=a.lastIndex;const m=/[ \t]*(.*)/sy;return m.lastIndex=h,s=m.exec(u),c+o+((s==n`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 164. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:1
- **Description:** exec()
- **Evidence (Line):** `import{v as Ju}from"./defaultSettingsView-D31xz8zv.js";import"./urlMatch-BYQrIQwR.js";var vi={export`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 165. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:1
- **Description:** exec()
- **Evidence (Line):** `import{v as Ju}from"./defaultSettingsView-D31xz8zv.js";import"./urlMatch-BYQrIQwR.js";var vi={export`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 166. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:1
- **Description:** exec()
- **Evidence (Line):** `import{v as Ju}from"./defaultSettingsView-D31xz8zv.js";import"./urlMatch-BYQrIQwR.js";var vi={export`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 167. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:1
- **Description:** exec()
- **Evidence (Line):** `import{v as Ju}from"./defaultSettingsView-D31xz8zv.js";import"./urlMatch-BYQrIQwR.js";var vi={export`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 168. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:4
- **Description:** exec()
- **Evidence (Line):** ``,t);i==-1&&(i=e.length);var o=e.slice(t,e.charAt(i-1)=="\r"?i-1:i),l=o.indexOf("\r");l!=-1?(n.push(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 169. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 170. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 171. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 172. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 173. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 174. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 175. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:24
- **Description:** exec()
- **Evidence (Line):** `outline: none; border-width: 0; outline: none; overflow: hidden; opacity: .05; filter: alpha(opacity`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 176. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:25
- **Description:** exec()
- **Evidence (Line):** ``;O.replaceSelection(q+q,null),S(O,-1),N=O.listSelections();for(var p=0;p<N.length;p++){var W=N[p].h`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 177. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:26
- **Description:** exec()
- **Evidence (Line):** ``+J}X=X*2,M.lastIndex=N.ch;var P=M.exec(z);if(P){var V=z.slice(0,P.index).split(``
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 178. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:28
- **Description:** exec()
- **Evidence (Line):** ``),G=N.line+V.length-1,c=V[V.length-1].length;return{from:pe(G,c),to:pe(G+F.length-1,F.length==1?c+F`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 179. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:31
- **Description:** exec()
- **Evidence (Line):** ``),c=p+F.length,T=F[F.length-1].length;return{from:pe(c,T),to:pe(c+G.length-1,G.length==1?T+G[0].len`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 180. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:32
- **Description:** exec()
- **Evidence (Line):** ``:J=="r"?"\r":J=="t"?"	":J=="\\"?"\\":W})}function S(p){var W=p.match(/^\/(.*)\/([a-z]*)$/);if(W)try`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 181. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:32
- **Description:** exec()
- **Evidence (Line):** ``:J=="r"?"\r":J=="t"?"	":J=="\\"?"\\":W})}function S(p){var W=p.match(/^\/(.*)\/([a-z]*)$/);if(W)try`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 182. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/codeMirrorModule-Ds_H_9Yq.js:32
- **Description:** exec()
- **Evidence (Line):** ``:J=="r"?"\r":J=="t"?"	":J=="\\"?"\\":W})}function S(p){var W=p.match(/^\/(.*)\/([a-z]*)$/);if(W)try`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 183. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:109
- **Description:** eval()
- **Evidence (Line):** `${n.stack}`,{e:{n:n.name,m:n.message,s:u}}}if(dA(n))return{d:n.toJSON()};if(pA(n))return{u:n.toJSON(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 184. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:109
- **Description:** eval()
- **Evidence (Line):** `${n.stack}`,{e:{n:n.name,m:n.message,s:u}}}if(dA(n))return{d:n.toJSON()};if(pA(n))return{u:n.toJSON(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 185. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:109
- **Description:** eval()
- **Evidence (Line):** `${n.stack}`,{e:{n:n.name,m:n.message,s:u}}}if(dA(n))return{d:n.toJSON()};if(pA(n))return{u:n.toJSON(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 186. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:109
- **Description:** eval()
- **Evidence (Line):** `${n.stack}`,{e:{n:n.name,m:n.message,s:u}}}if(dA(n))return{d:n.toJSON()};if(pA(n))return{u:n.toJSON(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 187. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:109
- **Description:** eval()
- **Evidence (Line):** `${n.stack}`,{e:{n:n.name,m:n.message,s:u}}}if(dA(n))return{d:n.toJSON()};if(pA(n))return{u:n.toJSON(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 188. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:52
- **Description:** exec()
- **Evidence (Line):** ``:this.value}}class Mr extends et{constructor(){super(...arguments),this.value=""}ASCIIMatch(e){retu`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 189. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:52
- **Description:** exec()
- **Evidence (Line):** ``:this.value}}class Mr extends et{constructor(){super(...arguments),this.value=""}ASCIIMatch(e){retu`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 190. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:59
- **Description:** exec()
- **Evidence (Line):** `rgb(0 0 0 / 25%) 0px 6px 12px`},N_=({diff:n,noTargetBlank:e,hideDetails:i})=>{const[r,l]=R.useState(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 191. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:65
- **Description:** exec()
- **Evidence (Line):** ``+l.gitDiff+"\n```"),d},[o,l],void 0);return n.errors.size?v.jsxs("div",{className:"fill",style:{ove`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 192. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:209
- **Description:** exec()
- **Evidence (Line):** ``,"sy")}catch{e=/(.*?)[ \t]*\r?\n/sy,i=/[ \t]*(.*?)[ \t]*\r?\n/sy}let r=e.exec(n);if(!r)return n;let`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 193. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:209
- **Description:** exec()
- **Evidence (Line):** ``,"sy")}catch{e=/(.*?)[ \t]*\r?\n/sy,i=/[ \t]*(.*?)[ \t]*\r?\n/sy}let r=e.exec(n);if(!r)return n;let`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 194. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/defaultSettingsView-D31xz8zv.js:211
- **Description:** exec()
- **Evidence (Line):** ``:(l+=o+r[1],o=" "),u=i.lastIndex;const f=/[ \t]*(.*)/sy;return f.lastIndex=u,r=f.exec(n),l+o+((r==n`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 195. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/xtermModule-CsJ4vdCR.js:7
- **Description:** exec()
- **Evidence (Line):** ``)}clearSelection(){this._model.clearSelection(),this._removeMouseDownListeners(),this.refresh(),thi`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 196. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/xtermModule-CsJ4vdCR.js:7
- **Description:** exec()
- **Evidence (Line):** ``)}clearSelection(){this._model.clearSelection(),this._removeMouseDownListeners(),this.refresh(),thi`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 197. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/xtermModule-CsJ4vdCR.js:8
- **Description:** exec()
- **Evidence (Line):** ``,n.VT="\v",n.FF="\f",n.CR="\r",n.SO="",n.SI="",n.DLE="",n.DC1="",n.DC2="",n.DC3="",n.DC4="",`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 198. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/lib/vite/traceViewer/assets/xtermModule-CsJ4vdCR.js:8
- **Description:** exec()
- **Evidence (Line):** ``,n.VT="\v",n.FF="\f",n.CR="\r",n.SO="",n.SI="",n.DLE="",n.DC1="",n.DC2="",n.DC3="",n.DC4="",`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 199. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/protocol.d.ts:22417
- **Description:** eval()
- **Evidence (Line):** `which includes eval(), Function(), setTimeout() and setInterval()`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 200. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:375
- **Description:** eval()
- **Evidence (Line):** `* [page.$eval(selector, pageFunction[, arg, options])](https://playwright.dev/docs/api/class-page#pa`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 201. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:381
- **Description:** eval()
- **Evidence (Line):** `* const searchValue = await page.$eval('#search', el => el.value);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 202. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:382
- **Description:** eval()
- **Evidence (Line):** `* const preloadHref = await page.$eval('link[rel=preload]', el => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 203. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:383
- **Description:** eval()
- **Evidence (Line):** `* const html = await page.$eval('.main-container', (e, suffix) => e.outerHTML + suffix, 'hello');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 204. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:385
- **Description:** eval()
- **Evidence (Line):** `* const preloadHrefTS = await page.$eval('link[rel=preload]', (el: HTMLLinkElement) => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 205. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:408
- **Description:** eval()
- **Evidence (Line):** `* [page.$eval(selector, pageFunction[, arg, options])](https://playwright.dev/docs/api/class-page#pa`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 206. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:414
- **Description:** eval()
- **Evidence (Line):** `* const searchValue = await page.$eval('#search', el => el.value);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 207. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:415
- **Description:** eval()
- **Evidence (Line):** `* const preloadHref = await page.$eval('link[rel=preload]', el => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 208. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:416
- **Description:** eval()
- **Evidence (Line):** `* const html = await page.$eval('.main-container', (e, suffix) => e.outerHTML + suffix, 'hello');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 209. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:418
- **Description:** eval()
- **Evidence (Line):** `* const preloadHrefTS = await page.$eval('link[rel=preload]', (el: HTMLLinkElement) => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 210. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:441
- **Description:** eval()
- **Evidence (Line):** `* [page.$eval(selector, pageFunction[, arg, options])](https://playwright.dev/docs/api/class-page#pa`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 211. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:447
- **Description:** eval()
- **Evidence (Line):** `* const searchValue = await page.$eval('#search', el => el.value);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 212. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:448
- **Description:** eval()
- **Evidence (Line):** `* const preloadHref = await page.$eval('link[rel=preload]', el => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 213. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:449
- **Description:** eval()
- **Evidence (Line):** `* const html = await page.$eval('.main-container', (e, suffix) => e.outerHTML + suffix, 'hello');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 214. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:451
- **Description:** eval()
- **Evidence (Line):** `* const preloadHrefTS = await page.$eval('link[rel=preload]', (el: HTMLLinkElement) => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 215. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:474
- **Description:** eval()
- **Evidence (Line):** `* [page.$eval(selector, pageFunction[, arg, options])](https://playwright.dev/docs/api/class-page#pa`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 216. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:480
- **Description:** eval()
- **Evidence (Line):** `* const searchValue = await page.$eval('#search', el => el.value);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 217. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:481
- **Description:** eval()
- **Evidence (Line):** `* const preloadHref = await page.$eval('link[rel=preload]', el => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 218. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:482
- **Description:** eval()
- **Evidence (Line):** `* const html = await page.$eval('.main-container', (e, suffix) => e.outerHTML + suffix, 'hello');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 219. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:484
- **Description:** eval()
- **Evidence (Line):** `* const preloadHrefTS = await page.$eval('link[rel=preload]', (el: HTMLLinkElement) => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 220. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:510
- **Description:** eval()
- **Evidence (Line):** `* [page.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-page#page-eval-`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 221. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:516
- **Description:** eval()
- **Evidence (Line):** `* const divCounts = await page.$$eval('div', (divs, min) => divs.length >= min, 10);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 222. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:540
- **Description:** eval()
- **Evidence (Line):** `* [page.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-page#page-eval-`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 223. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:546
- **Description:** eval()
- **Evidence (Line):** `* const divCounts = await page.$$eval('div', (divs, min) => divs.length >= min, 10);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 224. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:570
- **Description:** eval()
- **Evidence (Line):** `* [page.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-page#page-eval-`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 225. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:576
- **Description:** eval()
- **Evidence (Line):** `* const divCounts = await page.$$eval('div', (divs, min) => divs.length >= min, 10);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 226. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:600
- **Description:** eval()
- **Evidence (Line):** `* [page.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-page#page-eval-`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 227. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:606
- **Description:** eval()
- **Evidence (Line):** `* const divCounts = await page.$$eval('div', (divs, min) => divs.length >= min, 10);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 228. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5581
- **Description:** eval()
- **Evidence (Line):** `* [frame.$eval(selector, pageFunction[, arg, options])](https://playwright.dev/docs/api/class-frame#`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 229. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5587
- **Description:** eval()
- **Evidence (Line):** `* const searchValue = await frame.$eval('#search', el => el.value);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 230. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5588
- **Description:** eval()
- **Evidence (Line):** `* const preloadHref = await frame.$eval('link[rel=preload]', el => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 231. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5589
- **Description:** eval()
- **Evidence (Line):** `* const html = await frame.$eval('.main-container', (e, suffix) => e.outerHTML + suffix, 'hello');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 232. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5614
- **Description:** eval()
- **Evidence (Line):** `* [frame.$eval(selector, pageFunction[, arg, options])](https://playwright.dev/docs/api/class-frame#`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 233. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5620
- **Description:** eval()
- **Evidence (Line):** `* const searchValue = await frame.$eval('#search', el => el.value);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 234. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5621
- **Description:** eval()
- **Evidence (Line):** `* const preloadHref = await frame.$eval('link[rel=preload]', el => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 235. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5622
- **Description:** eval()
- **Evidence (Line):** `* const html = await frame.$eval('.main-container', (e, suffix) => e.outerHTML + suffix, 'hello');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 236. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5647
- **Description:** eval()
- **Evidence (Line):** `* [frame.$eval(selector, pageFunction[, arg, options])](https://playwright.dev/docs/api/class-frame#`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 237. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5653
- **Description:** eval()
- **Evidence (Line):** `* const searchValue = await frame.$eval('#search', el => el.value);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 238. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5654
- **Description:** eval()
- **Evidence (Line):** `* const preloadHref = await frame.$eval('link[rel=preload]', el => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 239. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5655
- **Description:** eval()
- **Evidence (Line):** `* const html = await frame.$eval('.main-container', (e, suffix) => e.outerHTML + suffix, 'hello');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 240. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5680
- **Description:** eval()
- **Evidence (Line):** `* [frame.$eval(selector, pageFunction[, arg, options])](https://playwright.dev/docs/api/class-frame#`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 241. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5686
- **Description:** eval()
- **Evidence (Line):** `* const searchValue = await frame.$eval('#search', el => el.value);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 242. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5687
- **Description:** eval()
- **Evidence (Line):** `* const preloadHref = await frame.$eval('link[rel=preload]', el => el.href);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 243. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5688
- **Description:** eval()
- **Evidence (Line):** `* const html = await frame.$eval('.main-container', (e, suffix) => e.outerHTML + suffix, 'hello');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 244. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5714
- **Description:** eval()
- **Evidence (Line):** `* [frame.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-frame#frame-ev`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 245. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5720
- **Description:** eval()
- **Evidence (Line):** `* const divsCounts = await frame.$$eval('div', (divs, min) => divs.length >= min, 10);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 246. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5744
- **Description:** eval()
- **Evidence (Line):** `* [frame.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-frame#frame-ev`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 247. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5750
- **Description:** eval()
- **Evidence (Line):** `* const divsCounts = await frame.$$eval('div', (divs, min) => divs.length >= min, 10);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 248. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5774
- **Description:** eval()
- **Evidence (Line):** `* [frame.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-frame#frame-ev`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 249. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5780
- **Description:** eval()
- **Evidence (Line):** `* const divsCounts = await frame.$$eval('div', (divs, min) => divs.length >= min, 10);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 250. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5804
- **Description:** eval()
- **Evidence (Line):** `* [frame.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-frame#frame-ev`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 251. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:5810
- **Description:** eval()
- **Evidence (Line):** `* const divsCounts = await frame.$$eval('div', (divs, min) => divs.length >= min, 10);`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 252. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:10862
- **Description:** eval()
- **Evidence (Line):** `* [page.$eval(selector, pageFunction[, arg, options])](https://playwright.dev/docs/api/class-page#pa`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 253. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11018
- **Description:** eval()
- **Evidence (Line):** `* [page.$eval(selector, pageFunction[, arg, options])](https://playwright.dev/docs/api/class-page#pa`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 254. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11103
- **Description:** eval()
- **Evidence (Line):** `* [elementHandle.$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-element`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 255. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11110
- **Description:** eval()
- **Evidence (Line):** `* expect(await tweetHandle.$eval('.like', node => node.innerText)).toBe('100');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 256. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11111
- **Description:** eval()
- **Evidence (Line):** `* expect(await tweetHandle.$eval('.retweets', node => node.innerText)).toBe('10');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 257. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11137
- **Description:** eval()
- **Evidence (Line):** `* [elementHandle.$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-element`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 258. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11144
- **Description:** eval()
- **Evidence (Line):** `* expect(await tweetHandle.$eval('.like', node => node.innerText)).toBe('100');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 259. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11145
- **Description:** eval()
- **Evidence (Line):** `* expect(await tweetHandle.$eval('.retweets', node => node.innerText)).toBe('10');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 260. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11171
- **Description:** eval()
- **Evidence (Line):** `* [elementHandle.$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-element`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 261. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11178
- **Description:** eval()
- **Evidence (Line):** `* expect(await tweetHandle.$eval('.like', node => node.innerText)).toBe('100');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 262. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11179
- **Description:** eval()
- **Evidence (Line):** `* expect(await tweetHandle.$eval('.retweets', node => node.innerText)).toBe('10');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 263. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11205
- **Description:** eval()
- **Evidence (Line):** `* [elementHandle.$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-element`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 264. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11212
- **Description:** eval()
- **Evidence (Line):** `* expect(await tweetHandle.$eval('.like', node => node.innerText)).toBe('100');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 265. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11213
- **Description:** eval()
- **Evidence (Line):** `* expect(await tweetHandle.$eval('.retweets', node => node.innerText)).toBe('10');`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 266. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11239
- **Description:** eval()
- **Evidence (Line):** `* [elementHandle.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-elemen`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 267. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11253
- **Description:** eval()
- **Evidence (Line):** `* expect(await feedHandle.$$eval('.tweet', nodes =>`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 268. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11280
- **Description:** eval()
- **Evidence (Line):** `* [elementHandle.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-elemen`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 269. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11294
- **Description:** eval()
- **Evidence (Line):** `* expect(await feedHandle.$$eval('.tweet', nodes =>`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 270. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11321
- **Description:** eval()
- **Evidence (Line):** `* [elementHandle.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-elemen`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 271. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11335
- **Description:** eval()
- **Evidence (Line):** `* expect(await feedHandle.$$eval('.tweet', nodes =>`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 272. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11362
- **Description:** eval()
- **Evidence (Line):** `* [elementHandle.$$eval(selector, pageFunction[, arg])](https://playwright.dev/docs/api/class-elemen`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 273. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/playwright/driver/package/types/types.d.ts:11376
- **Description:** eval()
- **Evidence (Line):** `* expect(await feedHandle.$$eval('.tweet', nodes =>`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 274. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pluggy/_caller.py:197
- **Description:** exec()
- **Evidence (Line):** `return self._hookexec(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 275. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pluggy/_caller.py:222
- **Description:** exec()
- **Evidence (Line):** `res = self._hookexec(self.name, self._hookimpls.copy(), kwargs, False)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 276. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pluggy/_caller.py:262
- **Description:** exec()
- **Evidence (Line):** `return self._hookexec(self.name, hookimpls, kwargs, firstresult)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 277. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pluggy/_caller.py:269
- **Description:** exec()
- **Evidence (Line):** `res = self._hookexec(self.name, [method], kwargs, False)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 278. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pluggy/_manager.py:174
- **Description:** exec()
- **Evidence (Line):** `def _hookexec(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 279. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pluggy/_manager.py:183
- **Description:** exec()
- **Evidence (Line):** `return self._inner_hookexec(hook_name, methods, kwargs, firstresult)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 280. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pluggy/_manager.py:587
- **Description:** exec()
- **Evidence (Line):** `def traced_hookexec(`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 281. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pygments/formatters/__init__.py:91
- **Description:** eval()
- **Evidence (Line):** `this method is equivalent to running ``eval()`` on the input file. The formatter is`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 282. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pygments/formatters/__init__.py:103
- **Description:** exec()
- **Evidence (Line):** `exec(f.read(), custom_namespace)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 283. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pygments/lexers/__init__.py:154
- **Description:** exec()
- **Evidence (Line):** `exec(f.read(), custom_namespace)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 284. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pygments/lexers/_julia_builtins.py:150
- **Description:** eval()
- **Evidence (Line):** `v = eval(Symbol(compl.mod))`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 285. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pygments/lexers/_julia_builtins.py:361
- **Description:** eval()
- **Evidence (Line):** `v = eval(Symbol(compl.mod))`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 286. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pygments/lexers/special.py:115
- **Description:** eval()
- **Evidence (Line):** `val = ast.literal_eval(val)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 287. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/pyparsing/results.py:66
- **Description:** eval()
- **Evidence (Line):** `print(f"{s} -> {fn(eval(s))}")`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 288. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/typing_extensions.py:1591
- **Description:** eval()
- **Evidence (Line):** `(unless you are familiar with how eval() and exec() work).  The`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 289. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/typing_extensions.py:4167
- **Description:** eval()
- **Evidence (Line):** `# as a way of emulating annotation scopes when calling `eval()``
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 290. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/typing_extensions.py:4172
- **Description:** eval()
- **Evidence (Line):** `value if not isinstance(value, str) else eval(value, globals, locals)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 291. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/typing_extensions.py:4219
- **Description:** eval()
- **Evidence (Line):** `# If we pass None to eval() below, the globals of this module are used.`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 292. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/typing_extensions.py:4231
- **Description:** eval()
- **Evidence (Line):** `# as a way of emulating annotation scopes when calling `eval()``
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 293. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/typing_extensions.py:4254
- **Description:** eval()
- **Evidence (Line):** `value = eval(code, globals, locals)`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 294. [Critical] Command Injection
- **File:** .venv-test/lib/python3.12/site-packages/typing_extensions.py:1591
- **Description:** exec()
- **Evidence (Line):** `(unless you are familiar with how eval() and exec() work).  The`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 295. [Critical] Command Injection
- **File:** python/pytagmanager/distribution/assets/pytagmanager.js:536
- **Description:** exec()
- **Evidence (Line):** `var match = /^(\d+)\.(\d+)\.(\d+)/.exec(String(value));`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 296. [Critical] Command Injection
- **File:** sdk/web/src/pytagmanager.js:536
- **Description:** exec()
- **Evidence (Line):** `var match = /^(\d+)\.(\d+)\.(\d+)/.exec(String(value));`
- **Exploit Scenario:** Attacker could execute arbitrary system commands
- **Fix Recommendation:** Avoid shell execution, use subprocess with shell=False and list args
- **Confidence:** High

### 297. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/coverage/lcovreport.py:45
- **Description:** MD5 usage
- **Evidence (Line):** `hashed = hashlib.md5(line.encode("utf-8"), usedforsecurity=False).digest()`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 298. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/coverage/lcovreport.py:45
- **Description:** Weak hash algorithm
- **Evidence (Line):** `hashed = hashlib.md5(line.encode("utf-8"), usedforsecurity=False).digest()`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 299. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/cryptography/hazmat/backends/openssl/backend.py:39
- **Description:** DES usage
- **Evidence (Line):** `# FIPS 140-3. To keep it simple we denylist any use of TripleDES (TDEA).`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 300. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/cryptography/hazmat/decrepit/ciphers/algorithms.py:29
- **Description:** DES usage
- **Evidence (Line):** `class TripleDES(BlockCipherAlgorithm):`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 301. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/cryptography/hazmat/decrepit/ciphers/algorithms.py:40
- **Description:** DES usage
- **Evidence (Line):** `"Single-key TripleDES (8-byte keys) is deprecated and "`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 302. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/cryptography/hazmat/decrepit/ciphers/algorithms.py:49
- **Description:** DES usage
- **Evidence (Line):** `"Two-key TripleDES (16-byte keys) is deprecated and "`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 303. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/cryptography/hazmat/decrepit/ciphers/algorithms.py:17
- **Description:** RC4 usage
- **Evidence (Line):** `class ARC4(CipherAlgorithm):`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 304. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/cryptography/x509/extensions.py:72
- **Description:** SHA1 usage
- **Evidence (Line):** `return hashlib.sha1(data).digest()`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 305. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/cryptography/x509/extensions.py:72
- **Description:** Weak hash algorithm
- **Evidence (Line):** `return hashlib.sha1(data).digest()`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 306. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/google/protobuf/proto_builder.py:69
- **Description:** SHA1 usage
- **Evidence (Line):** `fields_hash = hashlib.sha1(usedforsecurity=False)`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 307. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/google/protobuf/proto_builder.py:69
- **Description:** Weak hash algorithm
- **Evidence (Line):** `fields_hash = hashlib.sha1(usedforsecurity=False)`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 308. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/httplib2/__init__.py:266
- **Description:** MD5 usage
- **Evidence (Line):** `filemd5 = _md5(filename_bytes).hexdigest()`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 309. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/httplib2/__init__.py:477
- **Description:** MD5 usage
- **Evidence (Line):** `dig = _md5(`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 310. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/httplib2/__init__.py:585
- **Description:** MD5 usage
- **Evidence (Line):** `H = lambda x: _md5(x.encode("utf-8")).hexdigest()`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 311. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/oauthlib/oauth1/rfc5849/__init__.py:223
- **Description:** SHA1 usage
- **Evidence (Line):** `params.append(('oauth_body_hash', base64.b64encode(hashlib.sha1(request.body.encode('utf-8')).digest`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 312. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/oauthlib/oauth1/rfc5849/__init__.py:223
- **Description:** Weak hash algorithm
- **Evidence (Line):** `params.append(('oauth_body_hash', base64.b64encode(hashlib.sha1(request.body.encode('utf-8')).digest`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 313. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/oauthlib/oauth1/rfc5849/endpoints/base.py:190
- **Description:** SHA1 usage
- **Evidence (Line):** `valid_signature = signature.verify_rsa_sha1(request, rsa_key)`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 314. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/oauthlib/oauth1/rfc5849/endpoints/base.py:225
- **Description:** SHA1 usage
- **Evidence (Line):** `valid_signature = signature.verify_hmac_sha1(`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 315. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/oauthlib/oauth1/rfc5849/signature.py:469
- **Description:** SHA1 usage
- **Evidence (Line):** `def verify_hmac_sha1(request, client_secret=None, resource_owner_secret=None):`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 316. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/oauthlib/oauth1/rfc5849/signature.py:473
- **Description:** SHA1 usage
- **Evidence (Line):** `def sign_hmac_sha1(base_string, client_secret, resource_owner_secret):`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 317. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/oauthlib/oauth1/rfc5849/signature.py:754
- **Description:** SHA1 usage
- **Evidence (Line):** `def verify_rsa_sha1(request, rsa_public_key: str):`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 318. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/oauthlib/oauth1/rfc5849/signature.py:758
- **Description:** SHA1 usage
- **Evidence (Line):** `def sign_rsa_sha1(base_string, rsa_private_key):`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 319. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/oauthlib/oauth1/rfc5849/signature.py:410
- **Description:** Weak hash algorithm
- **Evidence (Line):** `'SHA-1': hashlib.sha1,`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 320. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/oauthlib/oauth2/rfc6749/tokens.py:111
- **Description:** Weak hash algorithm
- **Evidence (Line):** `h = hashlib.sha1`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 321. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/requests/auth.py:179
- **Description:** MD5 usage
- **Evidence (Line):** `return hashlib.md5(x, usedforsecurity=False).hexdigest()`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 322. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/requests/auth.py:187
- **Description:** SHA1 usage
- **Evidence (Line):** `return hashlib.sha1(x, usedforsecurity=False).hexdigest()`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 323. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/requests/auth.py:237
- **Description:** SHA1 usage
- **Evidence (Line):** `cnonce = hashlib.sha1(s, usedforsecurity=False).hexdigest()[:16]`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 324. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/requests/auth.py:179
- **Description:** Weak hash algorithm
- **Evidence (Line):** `return hashlib.md5(x, usedforsecurity=False).hexdigest()`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 325. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/requests/auth.py:187
- **Description:** Weak hash algorithm
- **Evidence (Line):** `return hashlib.sha1(x, usedforsecurity=False).hexdigest()`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High

### 326. [Medium] Weak Cryptography
- **File:** .venv-test/lib/python3.12/site-packages/requests/auth.py:237
- **Description:** Weak hash algorithm
- **Evidence (Line):** `cnonce = hashlib.sha1(s, usedforsecurity=False).hexdigest()[:16]`
- **Exploit Scenario:** Weak algorithms vulnerable to collision/brute force attacks
- **Fix Recommendation:** Use modern algorithms (SHA-256+, bcrypt/argon2 for passwords, secrets module for tokens)
- **Confidence:** High
