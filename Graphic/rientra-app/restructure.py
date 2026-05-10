import re

with open('src/components/HealthConditionWizard.tsx', 'r') as f:
    content = f.read()

# 1. Extract the header (lines 482-493)
header_pattern = r'(\s*\{\/\* Header \*\/\}\s*<div className="hc-wizard-header">.*?<button className="hc-wizard-close-btn" onClick=\{handleCloseClick\}><CloseIcon \/><\/button>\s*<\/div>)'
header_match = re.search(header_pattern, content, re.DOTALL)
header_str = header_match.group(1)
content = content.replace(header_str, '')

# 2. Add the texts block before the table container
# For step === 'select'
select_table_start = r'(<div ref=\{selectScrollRef\} className="hc-wizard-table-container">)'
new_select_text = '''
              <div className="hc-wizard-header">
                <div>
                  <h2 className="hc-wizard-title">Choose New Codes</h2>
                  <p className="hc-wizard-subtitle">Select additional codes to define the condition of the worker.</p>
                </div>
              </div>
              \\1'''
content = re.sub(select_table_start, new_select_text, content)

# For step === 'review'
review_table_start = r'(<div ref=\{reviewScrollRef\} className="hc-wizard-review-container">)'
new_review_text = '''
              <div className="hc-wizard-header">
                <div>
                  <h2 className="hc-wizard-title">Review Changes</h2>
                  <p className="hc-wizard-subtitle">Select the qualifier number regarding each ICF code.</p>
                </div>
              </div>
              \\1'''
content = re.sub(review_table_start, new_review_text, content)

# 3. Add the close button back to the toolbars
# In select toolbar:
select_toolbar_end = r'(<\/div>\s*\{\/\* Filters Group \*\/\})'
content = re.sub(select_toolbar_end, r'\1', content) 
# Wait, let's just replace the div className="hc-wizard-toolbar" with one that has justify-content: space-between
# We'll add the close button at the end of the toolbars.
select_toolbar_close = r'(<FilterIcon \/> Filters:\s*<\/div>.*?<\/div>\s*<\/div>\s*)(<div className="hc-wizard-header">)'
# Actually, it's easier to just append the close button inside the toolbar.
content = re.sub(r'(<div className="hc-wizard-toolbar">)', r'\1\n                <div style={{ flex: 1 }} />\n                <button className="hc-wizard-close-btn" onClick={handleCloseClick} style={{ alignSelf: "flex-start", marginTop: "-4px" }}><CloseIcon /></button>', content)

content = re.sub(r'(<div className="hc-review-toolbar">)', r'\1\n                <div style={{ flex: 1 }} />\n                <button className="hc-wizard-close-btn" onClick={handleCloseClick} style={{ alignSelf: "flex-start", marginTop: "-4px" }}><CloseIcon /></button>', content)

with open('src/components/HealthConditionWizard.tsx', 'w') as f:
    f.write(content)
