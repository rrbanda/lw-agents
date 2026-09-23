# Test Specification Template

When delegating test generation to OpenCode, the agent MUST build a
specification using this template. Pass the filled template as the
OpenCode instruction — NOT generated code.

## Template

```
Create a JUnit 5 reproducer test with these requirements:

CVE: <CVE-ID>
Component: <groupId:artifactId>
Vulnerable class: <fully qualified class name>
Vulnerable method: <method name and signature>
CWE: <CWE-ID> (<CWE name>)

Vulnerability: <1-2 sentence description of what's wrong>

Test file path: src/test/java/<package path>/Cve<YYYY><NNNNN>ReproducerTest.java

Test requirements:
- <What malicious input to construct>
- <What code path to exercise>
- <What assertion proves the fix works>

Existing coverage: <none | partial | full>
- <If partial/full: what existing test file covers, what it misses>

Action: <new_file | add_method | enhance_existing>

Additional context:
- Fixed in version: <version>
- Upstream fix commit: <URL if available>
- The test should FAIL on the vulnerable version and PASS on the fixed version
- If enhancing: add edge cases, boundary conditions, different attack vectors
```

## Example: CVE-2024-29025 (Netty)

```
Create a JUnit 5 reproducer test with these requirements:

CVE: CVE-2024-29025
Component: io.netty:netty-codec-http
Vulnerable class: io.netty.handler.codec.http.HttpObjectDecoder
Vulnerable method: decode(ChannelHandlerContext, ByteBuf, List<Object>)
CWE: CWE-400 (Uncontrolled Resource Consumption)

Vulnerability: HttpObjectDecoder does not enforce a limit on the total
size of HTTP headers. An attacker can send a request with many headers
that collectively exceed available memory, causing resource exhaustion.

Test file path: src/test/java/io/netty/handler/codec/http/Cve202429025ReproducerTest.java

Test requirements:
- Construct an HTTP request with headers totaling >8192 bytes
- Pass it through HttpObjectDecoder
- Assert that the decoder either rejects the request or throws
  TooLongHttpHeaderException (not OutOfMemoryError)

Additional context:
- Fixed in version: 4.1.108.Final
- Upstream fix commit: https://github.com/netty/netty/commit/0d0c6ed
- The test should FAIL on 4.1.100.Final and PASS on 4.1.108.Final
```

## Example: CVE-2024-22262 (Spring Web)

```
Create a JUnit 5 reproducer test with these requirements:

CVE: CVE-2024-22262
Component: org.springframework:spring-web
Vulnerable class: org.springframework.web.util.UriComponentsBuilder
Vulnerable method: fromUriString(String)
CWE: CWE-601 (URL Redirection to Untrusted Site)

Vulnerability: UriComponentsBuilder.fromUriString does not properly
validate the host component, allowing an attacker to craft a URL that
redirects to a malicious site when the application builds redirect URLs.

Test file path: src/test/java/org/springframework/web/util/Cve202422262ReproducerTest.java

Test requirements:
- Construct a URL string with a crafted host component (e.g. "//evil.com")
- Pass it through UriComponentsBuilder.fromUriString()
- Assert that the resulting URI does NOT point to evil.com
  (the fix should normalize or reject the malicious host)

Additional context:
- Fixed in version: 6.1.6
- The test should FAIL on 6.1.5 and PASS on 6.1.6
```

## Example: Enhancing Existing Coverage (CVE-2024-22262)

When tests already exist for the vulnerable class:

```
Create a JUnit 5 reproducer test with these requirements:

CVE: CVE-2024-22262
Component: org.springframework:spring-web
Vulnerable class: org.springframework.web.util.UriComponentsBuilder
Vulnerable method: fromUriString(String)
CWE: CWE-601 (URL Redirection to Untrusted Site)

Vulnerability: UriComponentsBuilder.fromUriString does not properly
validate the host component, allowing redirect to malicious sites.

Test file path: src/test/java/org/springframework/web/util/Cve202422262ReproducerTest.java

Existing coverage: partial (UriComponentsBuilderTests.java exists,
tests basic parsing but does NOT test malicious host injection)

Action: new_file (create separate CVE-specific reproducer alongside existing tests)

Test requirements:
- Test "//evil.com" host injection via fromUriString
- Test double-slash bypass: "///evil.com"
- Test backslash variant: "/\\evil.com"
- Test encoded variants: "/%2Fevil.com"
- Assert none of the above redirect to evil.com

Additional context:
- Fixed in version: 6.1.6
- The existing UriComponentsBuilderTests.java tests valid URLs only.
  This reproducer specifically targets the malicious host injection path.
```

## How the Agent Builds the Spec

The agent fills this template using data from its investigation:

| Field | Source |
|-------|--------|
| CVE | From the user request |
| Component | From parse_maven_purl() |
| Vulnerable class | From fetch_commit_diff() — look at which files changed |
| Vulnerable method | From the diff hunks — look at modified methods |
| CWE | From lookup_nvd() — cwe_id field |
| Vulnerability | From the CVE description (NVD or OSV) |
| Test file path | Derived from the vulnerable class package |
| Test requirements | From CWE pattern + diff analysis |
| Fixed version | From lookup_osv() or search_github_advisory() |
| Upstream commit | From search_github_advisory() or search_fix_commits() |
| Existing coverage | From `find src/test -name '*Test.java'` + `grep -rl 'ClassName' src/test/` |
| Action | Derived: none→new_file, partial→new_file or add_method, full→enhance_existing |
