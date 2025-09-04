# ADR-003: Test Documentation and Timestamp Standards

## Status
Accepted

## Date
2025-01-02

## Context
As our test suite grows and becomes more complex, we need consistent documentation standards to ensure tests remain maintainable, traceable, and purposeful. Currently, tests lack consistent documentation about their purpose, last update time, and expected outcomes, making it difficult to:

1. **Understand test purpose** when reviewing or debugging
2. **Track test maintenance** and identify stale tests
3. **Verify test relevance** to current system requirements
4. **Maintain test quality** over time

## Decision
All test files in the Editora v2 project must include standardized documentation headers with the following mandatory elements:

### **Required Test Header Format**
```python
"""
Test: [Descriptive Test Name]
Purpose: [Clear description of what this test validates or demonstrates]
Last Updated: YYYY-MM-DD HH:MM:SS UTC
Expected: [What the test should reveal, prove, or demonstrate]
Author: [Original author name]
Related: [Related ADRs, issues, or documentation]
"""
```

### **Documentation Standards**

#### **1. Test Name**
- Must be descriptive and specific
- Should indicate what is being tested
- Examples:
  - ✅ "Google Video Intelligence Raw Labels Analysis"
  - ✅ "ADR-002 Hybrid Classification Pipeline Validation"
  - ❌ "Video Test"
  - ❌ "Test Classification"

#### **2. Purpose Statement**
- Must clearly explain why the test exists
- Should describe what the test validates or demonstrates
- Must be understandable by any team member
- Examples:
  - ✅ "Extract and display raw labels from Google Video Intelligence API to analyze classification accuracy"
  - ✅ "Validate that the ADR-002 hybrid pipeline correctly combines Video Intelligence and Vision API results"
  - ❌ "Tests video stuff"

#### **3. Last Updated Timestamp**
- Must use ISO 8601 format: `YYYY-MM-DD HH:MM:SS UTC`
- Must be updated whenever test code is modified
- Must reflect the actual time of the last meaningful change
- Examples:
  - ✅ "2025-01-02 15:30:00 UTC"
  - ✅ "2024-12-19 09:15:30 UTC"

#### **4. Expected Outcomes**
- Must describe what the test should reveal or demonstrate
- Should help reviewers understand test success criteria
- Must be specific enough to guide test interpretation
- Examples:
  - ✅ "Raw scene labels with confidence scores and timestamps from Google API"
  - ✅ "7+ distinct scenes detected with >70% confidence scores"
  - ❌ "Good results"

#### **5. Author (Optional but Recommended)**
- Original test creator for accountability and context
- Helps with maintenance questions

#### **6. Related (Optional)**
- Links to relevant ADRs, issues, or documentation
- Helps understand test context and dependencies

### **Implementation Requirements**

#### **For New Tests**
- All new test files must include the complete header
- Tests without proper headers will not pass code review
- Header must be the first docstring in the file

#### **For Existing Tests**
- Existing tests should be updated with headers during maintenance
- Priority for header updates:
  1. Critical production tests
  2. Frequently modified tests
  3. Complex or poorly documented tests

#### **Header Validation**
- Code review must verify header completeness
- Automated linting should check for header presence (future enhancement)
- Headers must be updated when test logic changes

### **Examples**

#### **Good Test Header**
```python
"""
Test: Google Video Intelligence Raw Labels Analysis
Purpose: Extract and display raw labels from Google Video Intelligence API for calibration analysis.
         This test bypasses all ADR-002 post-processing to show exactly what Google returns.
Last Updated: 2025-01-02 15:30:00 UTC
Expected: Raw segment and frame labels with confidence scores, timestamps, and shot detection data
Author: Backend Team
Related: ADR-002 (Video Intelligence Integration)
"""
```

#### **Minimal Acceptable Header**
```python
"""
Test: Basic Image Classification Validation
Purpose: Verify that Google Vision API correctly classifies real estate property images
Last Updated: 2025-01-02 14:20:00 UTC
Expected: Room classifications with >80% confidence for kitchen, bedroom, bathroom images
"""
```

## Rationale

### **1. Improved Maintainability**
- Clear documentation reduces time needed to understand test purpose
- Timestamps help identify tests that may need updates
- Expected outcomes guide test interpretation and debugging

### **2. Better Test Quality**
- Forces test authors to think clearly about test purpose
- Helps identify redundant or unclear tests
- Provides context for test modifications

### **3. Enhanced Team Collaboration**
- New team members can quickly understand test suite
- Clear expectations help with test result interpretation
- Consistent format improves code review efficiency

### **4. Traceability and Compliance**
- Timestamps provide audit trail for test changes
- Purpose statements link tests to business requirements
- Related field connects tests to architectural decisions

## Consequences

### **Positive**
1. **📚 Better Documentation**: Clear, consistent test documentation across the project
2. **🔍 Improved Debugging**: Easier to understand test failures and purpose
3. **⏰ Maintenance Tracking**: Easy identification of stale or outdated tests
4. **👥 Team Efficiency**: Faster onboarding and collaboration
5. **🎯 Test Quality**: Forces clear thinking about test purpose and expectations

### **Negative**
1. **📝 Additional Overhead**: Extra documentation work for developers
2. **🔄 Maintenance Burden**: Need to update timestamps when modifying tests
3. **📏 Consistency Enforcement**: Requires discipline to maintain standards

### **Mitigation Strategies**
1. **Code Review Enforcement**: Make header completeness part of review checklist
2. **Template Provision**: Provide header templates for easy copying
3. **Gradual Implementation**: Update headers during normal maintenance cycles
4. **Tool Support**: Consider automated header validation in CI/CD pipeline

## Implementation Plan

### **Phase 1: Standards Definition ✅**
- [x] Define header format and requirements
- [x] Create documentation and examples
- [x] Establish enforcement guidelines

### **Phase 2: New Test Implementation**
- [ ] Apply standards to all new tests starting immediately
- [ ] Create header templates for common test types
- [ ] Update code review checklist to include header verification

### **Phase 3: Existing Test Updates**
- [ ] Identify high-priority existing tests for header updates
- [ ] Update critical production tests first
- [ ] Gradually update remaining tests during maintenance

### **Phase 4: Automation (Future)**
- [ ] Implement automated header validation
- [ ] Create tools to help maintain timestamp accuracy
- [ ] Add header completeness to CI/CD pipeline

## Success Metrics

### **Compliance Metrics**
- **New Tests**: 100% of new tests have complete headers
- **Existing Tests**: 80% of existing tests updated within 6 months
- **Code Review**: Header completeness checked in 100% of test-related reviews

### **Quality Metrics**
- **Test Understanding**: Reduced time to understand test purpose (measured via team feedback)
- **Maintenance Efficiency**: Faster identification of tests needing updates
- **Documentation Quality**: Improved clarity of test documentation (measured via team surveys)

## Related Standards

### **File Naming Conventions**
- Test files should use descriptive names that match the test purpose
- Example: `test_google_video_intelligence_raw.py` (matches test name)

### **Code Organization**
- Test documentation should be consistent with overall code documentation standards
- Headers should complement, not duplicate, function-level docstrings

## Review and Evolution

### **Review Schedule**
- **3 months**: Assess compliance and adoption rates
- **6 months**: Review effectiveness and gather team feedback
- **12 months**: Consider automation enhancements and standard updates

### **Evolution Path**
1. **Short-term**: Focus on compliance and basic adoption
2. **Medium-term**: Add automation and tooling support
3. **Long-term**: Integrate with broader documentation and quality systems

---

**Decision made by**: Development Team  
**Stakeholders**: Backend Engineers, QA Engineers, DevOps Team  
**Implementation Lead**: Backend Engineering Team  
**Review Date**: 2025-04-02 (3 months from decision)
