import re

with open('src/components/HealthConditionWizard.tsx', 'r') as f:
    content = f.read()

# For step === 'select'
# Change `<div className="hc-wizard-box">` right after `{step === 'select' && (` to `<>`
content = re.sub(r'(\{step === \'select\' && \(\s*)<div className="hc-wizard-box">', r'\1<>', content)

# Insert `<div className="hc-wizard-box">` right before `<div ref={selectScrollRef} className="hc-wizard-table-container">`
content = re.sub(r'(<div ref=\{selectScrollRef\} className="hc-wizard-table-container">)', r'<div className="hc-wizard-box">\n              \1', content)

# Change the closing `</div>` right before `{step === 'review' && (` to `</>`
content = re.sub(r'(<\/div>\s*)(\s*\{step === \'review\' && \()', r'</>\n\2', content)

# For step === 'review'
content = re.sub(r'(\{step === \'review\' && \(\s*)<div className="hc-wizard-box">', r'\1<>', content)

content = re.sub(r'(<div ref=\{reviewScrollRef\} className="hc-wizard-review-container">)', r'<div className="hc-wizard-box">\n              \1', content)

content = re.sub(r'(<\/div>\s*)(\s*\{\(step === \'saving\' \|\| step === \'done\'\) && \()', r'</>\n\2', content)

with open('src/components/HealthConditionWizard.tsx', 'w') as f:
    f.write(content)
