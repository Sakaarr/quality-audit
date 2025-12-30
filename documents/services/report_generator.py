"""
Report Generator Service

Generates beautiful HTML reports from validation data stored in JSON format.
"""
import json
from typing import Dict, List, Any, Optional
from datetime import datetime


def calculate_document_health_score(report_data: Dict[str, Any]) -> float:
    """
    Calculate overall document health score (0-100) based on validation results.
    
    Args:
        report_data: Complete report data from JSON file
        
    Returns:
        Health score as float between 0 and 100
    """
    if not report_data or 'reports' not in report_data:
        return 0.0
    
    reports = report_data.get('reports', {})
    
    # If no reports exist, return neutral score
    if not reports:
        return 50.0
    
    total_score = 0.0
    score_count = 0
    
    # Grammar validation scoring
    grammar_data = reports.get('pdf-grammer-validation') or reports.get('docx-grammer-validation') or []
    if grammar_data:
        total_errors = 0
        total_words = 0
        total_readability = 0
        page_count = len(grammar_data)
        
        for page in grammar_data:
            # Count errors
            spelling_errors = len(page.get('spelling_errors', []))
            grammar_errors = len(page.get('grammar_errors', []))
            total_errors += spelling_errors + grammar_errors
            
            # Estimate word count from original text
            original_text = page.get('original_text', '')
            words = len(original_text.split())
            total_words += words
            
            # Get readability score
            readability = page.get('readability_scores', {})
            flesch_score = readability.get('flesch_reading_ease', 50)
            total_readability += flesch_score
        
        # Calculate grammar score (fewer errors = higher score)
        if total_words > 0:
            error_rate = total_errors / total_words
            grammar_score = max(0, 100 - (error_rate * 1000))  # Penalize errors
        else:
            grammar_score = 50
        
        # Calculate readability score (normalize Flesch to 0-100)
        avg_readability = total_readability / page_count if page_count > 0 else 50
        readability_score = min(100, max(0, avg_readability))
        
        # Weighted average
        total_score += (grammar_score * 0.6 + readability_score * 0.4)
        score_count += 1
    
    # Math validation scoring
    math_data = reports.get('math_validation', {})
    if math_data:
        # Check for AI validation format
        if 'overall_assessment' in math_data:
            total_score += math_data['overall_assessment'].get('accuracy_percentage', 0)
        # Check for Regex validation format
        elif 'calculations' in math_data:
            total_legacy = len(math_data['calculations'])
            correct_legacy = sum(1 for c in math_data['calculations'] if c.get('is_correct'))
            if total_legacy > 0:
                total_score += (correct_legacy / total_legacy) * 100
            else:
                total_score += 100 # No calculations found = perfect? or neutral.
        else:
            # Fallback simple status
            status = math_data.get('status', 'error')
            if status == 'success':
                total_score += 100
            elif status == 'error':
                total_score += 0
            else:
                total_score += 50
        score_count += 1
        
    # Code Validation scoring
    code_data = reports.get('code_validation', {})
    if code_data:
        overall = code_data.get('overall_assessment', {})
        total_score += overall.get('accuracy_percentage', 0)
        score_count += 1
        
    # Accessibility scoring
    acc_data = reports.get('accessibility_validation', {})
    if acc_data:
        report = acc_data.get('report', {}) # Wrapper from view
        if not report: 
             report = acc_data
        total_score += report.get('accessibility_score', 0)
        score_count += 1
        
    # Section Validation scoring
    sec_data = reports.get('section_validation', {})
    if sec_data:
        total_score += sec_data.get('completeness_score', 0)
        score_count += 1
    
    # Calculate final score
    if score_count > 0:
        final_score = total_score / score_count
    else:
        final_score = 50.0
    
    return round(final_score, 2)


def generate_error_summary(grammar_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate summary statistics for errors across all pages.
    
    Args:
        grammar_data: List of page validation results
        
    Returns:
        Dictionary with error statistics
    """
    total_spelling = 0
    total_grammar = 0
    total_pages = len(grammar_data)
    
    spelling_by_type = {}
    grammar_by_type = {}
    
    for page in grammar_data:
        spelling_errors = page.get('spelling_errors', [])
        grammar_errors = page.get('grammar_errors', [])
        
        total_spelling += len(spelling_errors)
        total_grammar += len(grammar_errors)
        
        # Categorize errors
        for error in spelling_errors:
            msg = error.get('message', 'Unknown')
            spelling_by_type[msg] = spelling_by_type.get(msg, 0) + 1
        
        for error in grammar_errors:
            msg = error.get('message', 'Unknown')
            grammar_by_type[msg] = grammar_by_type.get(msg, 0) + 1
    
    return {
        'total_spelling_errors': total_spelling,
        'total_grammar_errors': total_grammar,
        'total_errors': total_spelling + total_grammar,
        'total_pages': total_pages,
        'avg_errors_per_page': round((total_spelling + total_grammar) / total_pages, 2) if total_pages > 0 else 0,
        'spelling_by_type': spelling_by_type,
        'grammar_by_type': grammar_by_type
    }


def generate_readability_chart_data(grammar_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Prepare readability data for chart visualization.
    
    Args:
        grammar_data: List of page validation results
        
    Returns:
        Dictionary with chart-ready data
    """
    pages = []
    flesch_scores = []
    grade_levels = []
    
    for page in grammar_data:
        page_num = page.get('page', 0)
        readability = page.get('readability_scores', {})
        
        pages.append(f"Page {page_num}")
        flesch_scores.append(readability.get('flesch_reading_ease', 0))
        grade_levels.append(readability.get('flesch_kincaid_grade', 0))
    
    return {
        'labels': pages,
        'flesch_reading_ease': flesch_scores,
        'flesch_kincaid_grade': grade_levels
    }


def format_error_details(error: Dict[str, Any], error_type: str) -> str:
    """
    Format individual error for HTML display.
    
    Args:
        error: Error dictionary
        error_type: 'spelling' or 'grammar'
        
    Returns:
        HTML string for error display
    """
    error_text = error.get('error_text', '')
    message = error.get('message', 'No description')
    suggestion = error.get('suggestion', '')
    
    label = 'SPELLING' if error_type == 'spelling' else 'GRAMMAR'
    color = '#d32f2f' if error_type == 'spelling' else '#f57c00'
    
    html = f'''
    <div class="error-item" style="border-left: 3px solid {color};">
        <div class="error-header">
            <span class="error-type">[{label}]</span>
            <span class="error-text">"{error_text}"</span>
        </div>
        <div class="error-message">{message}</div>
        {f'<div class="error-suggestion">Suggestion: <strong>{suggestion}</strong></div>' if suggestion else ''}
    </div>
    '''
    return html


def generate_html_report(report_data: Dict[str, Any]) -> str:
    """
    Generate complete HTML report from validation data.
    
    Args:
        report_data: Complete report data from JSON file
        
    Returns:
        HTML string for the report
    """
    reports = report_data.get('reports', {})
    
    # If no reports, return empty state
    if not reports:
        return generate_empty_report()
    
    # Calculate metrics
    health_score = calculate_document_health_score(report_data)
    grammar_data = reports.get('pdf-grammer-validation') or reports.get('docx-grammer-validation') or []
    math_data = reports.get('math_validation', {})
    code_data = reports.get('code_validation', {})
    section_data = reports.get('section_validation', {})
    
    error_summary = generate_error_summary(grammar_data) if grammar_data else {}
    chart_data = generate_readability_chart_data(grammar_data) if grammar_data else {}
    
    # Generate timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Build HTML
    html = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document Quality Audit Report</title>
    <style>
        {get_report_styles()}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header class="report-header">
            <h1>Document Quality Audit Report</h1>
            <p class="timestamp">Generated on: {timestamp}</p>
        </header>
        
        

        <!-- Page-by-Page Analysis -->
        {generate_page_analysis(grammar_data) if grammar_data else ''}
        
        <!-- Math Validation -->
        {generate_math_validation_section(math_data) if math_data else ''}
        
        <!-- Code Validation -->
        {generate_code_validation_section(code_data) if code_data else ''}
        
        <!-- Section Validation -->
        <!-- Section Validation -->
        {generate_section_validation_section(section_data) if section_data else ''}

        <!-- Accessibility Validation -->
        {generate_accessibility_section(reports.get('accessibility_validation', {})) if reports.get('accessibility_validation') else ''}
        
        <!-- Google Search Validation -->
        {generate_google_search_section(reports.get('google_search_validation', {})) if reports.get('google_search_validation') else ''}
        
        <!-- Visual Validation -->
        {generate_visual_validation_section(reports.get('visual_validation', {})) if reports.get('visual_validation') else ''}

        <!-- Title Validation -->
        {generate_title_validation_section(reports.get('title_validation', {})) if reports.get('title_validation') else ''}
        
        <!-- Reference Validation -->
        {generate_reference_validation_section(reports.get('reference_validation', {})) if reports.get('reference_validation') else ''}
        
        <!-- Formatting Validation -->
        {generate_formatting_validation_section(reports.get('formatting_validation', {})) if reports.get('formatting_validation') else ''}
        
        <!-- Footer -->
        <footer class="report-footer">
            <p>Quality Audit System © {datetime.now().year}</p>
        </footer>
    </div>
    
    <script>
        {get_report_scripts()}
    </script>
</body>
</html>
    '''
    
    return html


def generate_empty_report() -> str:
    """Generate HTML for empty report state."""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document Quality Audit Report</title>
    <style>
        {get_report_styles()}
    </style>
</head>
<body>
    <div class="container">
        <header class="report-header">
            <h1>Document Quality Audit Report</h1>
            <p class="timestamp">Generated on: {timestamp}</p>
        </header>
        
        <section class="empty-state">
            <div class="empty-icon">[ ]</div>
            <h2>No Validation Data Available</h2>
            <p>This document has not been analyzed yet. Please run validation checks to generate a report.</p>
        </section>
        
        <footer class="report-footer">
            <p>Quality Audit System © {datetime.now().year}</p>
        </footer>
    </div>
</body>
</html>
    '''


def generate_readability_section(chart_data: Dict[str, Any]) -> str:
    """Generate readability trends section HTML."""
    labels = json.dumps(chart_data.get('labels', []))
    flesch_scores = json.dumps(chart_data.get('flesch_reading_ease', []))
    grade_levels = json.dumps(chart_data.get('flesch_kincaid_grade', []))
    
    return f'''
    <section class="readability-section">
        <h2>1. Readability Analysis</h2>
        <p>The following chart illustrates the readability metrics across all pages of the document.</p>
        <div class="chart-container">
            <canvas id="readabilityChart"></canvas>
        </div>
        <script>
            const ctx = document.getElementById('readabilityChart').getContext('2d');
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: {labels},
                    datasets: [{{
                        label: 'Flesch Reading Ease',
                        data: {flesch_scores},
                        borderColor: '#000000',
                        backgroundColor: 'rgba(0, 0, 0, 0.05)',
                        tension: 0.3,
                        borderWidth: 2
                    }}, {{
                        label: 'Grade Level',
                        data: {grade_levels},
                        borderColor: '#666666',
                        backgroundColor: 'rgba(102, 102, 102, 0.05)',
                        tension: 0.3,
                        borderWidth: 2,
                        borderDash: [5, 5]
                    }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{
                            labels: {{ color: '#000000', font: {{ size: 11 }} }}
                        }}
                    }},
                    scales: {{
                        y: {{
                            ticks: {{ color: '#000000', font: {{ size: 10 }} }},
                            grid: {{ color: 'rgba(0, 0, 0, 0.1)' }}
                        }},
                        x: {{
                            ticks: {{ color: '#000000', font: {{ size: 10 }} }},
                            grid: {{ color: 'rgba(0, 0, 0, 0.1)' }}
                        }}
                    }}
                }}
            }});
        </script>
    </section>
    '''


def generate_page_analysis(grammar_data: List[Dict[str, Any]]) -> str:
    """Generate page-by-page analysis section HTML."""
    pages_html = []
    
    for page in grammar_data:
        page_num = page.get('page', 0)
        spelling_errors = page.get('spelling_errors', [])
        grammar_errors = page.get('grammar_errors', [])
        readability = page.get('readability_scores', {})
        
        errors_html = []
        for error in spelling_errors:
            errors_html.append(format_error_details(error, 'spelling'))
        for error in grammar_errors:
            errors_html.append(format_error_details(error, 'grammar'))
        
        page_html = f'''
        <div class="page-analysis">
            <h3>Page {page_num}</h3>
            <div class="readability-metrics">
                <span class="metric">Flesch Reading Ease: <strong>{readability.get('flesch_reading_ease', 'N/A')}</strong></span>
                <span class="metric">Grade Level: <strong>{readability.get('flesch_kincaid_grade', 'N/A')}</strong></span>
                <span class="metric">Errors: <strong>{len(spelling_errors) + len(grammar_errors)}</strong></span>
            </div>
            <div class="errors-container">
                {''.join(errors_html) if errors_html else '<p class="no-errors">No errors found on this page</p>'}
            </div>
        </div>
        '''
        pages_html.append(page_html)
    
    return f'''
    <section class="page-analysis-section">
        <h2>1. Detailed Page Analysis</h2>
        <p>This section provides a comprehensive breakdown of errors and readability metrics for each page.</p>
        {''.join(pages_html)}
    </section>
    '''


def generate_math_validation_section(math_data: Dict[str, Any]) -> str:
    """Generate math validation section HTML."""
    status = math_data.get('status', 'unknown')
    message = math_data.get('message', 'No information available')
    model = math_data.get('model', 'N/A')
    
    status_icon = '[SUCCESS]' if status == 'success' else '[ERROR]' if status == 'error' else '[WARNING]'
    status_color = '#4ecdc4' if status == 'success' else '#ff6b6b' if status == 'error' else '#ffd93d'
    
    return f'''
    <section class="math-validation-section">
        <h2>2. Mathematical Validation</h2>
        <div class="math-status" style="border-left: 4px solid {status_color};">
            <div class="status-header">
                <span class="status-icon">{status_icon}</span>
                <span class="status-text">Validation Status: <strong>{status.upper()}</strong></span>
            </div>
            <div class="status-message"><strong>Result:</strong> {message}</div>
            <div class="status-meta">Validation Model: {model}</div>
        </div>
    </section>
    '''


def generate_code_validation_section(code_data: Dict[str, Any]) -> str:
    """Generate code validation section HTML."""
    if not code_data or code_data.get('status') != 'success':
        return ''
    
    validations = code_data.get('validations', [])
    overall = code_data.get('overall_assessment', {})
    total_snippets = code_data.get('total_code_snippets_found', 0)
    
    # Generate validation items HTML
    validation_items = []
    for idx, validation in enumerate(validations, 1):
        code = validation.get('code', '')
        language = validation.get('language', 'unknown')
        location = validation.get('location', 'Unknown')
        is_valid = validation.get('is_valid', False)
        confidence = validation.get('confidence_score', 0)
        reasoning = validation.get('reasoning', '')
        issues = validation.get('issues', [])
        suggestions = validation.get('suggestions', [])
        
        status_badge = 'VALID' if is_valid else 'INVALID'
        status_color = '#2e7d32' if is_valid else '#d32f2f'
        
        issues_html = ''
        if issues:
            issues_list = ''.join([f'<li>{issue}</li>' for issue in issues])
            issues_html = f'''
            <div class="code-issues">
                <strong>Issues:</strong>
                <ul>{issues_list}</ul>
            </div>
            '''
        
        suggestions_html = ''
        if suggestions:
            suggestions_list = ''.join([f'<li>{suggestion}</li>' for suggestion in suggestions])
            suggestions_html = f'''
            <div class="code-suggestions">
                <strong>Suggestions:</strong>
                <ul>{suggestions_list}</ul>
            </div>
            '''
        
        validation_html = f'''
        <div class="code-validation-item">
            <div class="code-header">
                <span class="code-number">Snippet {idx}</span>
                <span class="code-location">{location}</span>
                <span class="code-language">{language.upper()}</span>
                <span class="code-status" style="background: {status_color};">{status_badge}</span>
            </div>
            <pre class="code-snippet"><code>{code}</code></pre>
            <div class="code-analysis">
                <div class="code-confidence">Confidence: <strong>{int(confidence * 100)}%</strong></div>
                <div class="code-reasoning">{reasoning}</div>
                {issues_html}
                {suggestions_html}
            </div>
        </div>
        '''
        validation_items.append(validation_html)
    
    # Overall assessment
    valid_count = overall.get('valid_snippets', 0)
    invalid_count = overall.get('invalid_snippets', 0)
    accuracy = overall.get('accuracy_percentage', 0)
    avg_confidence = overall.get('average_confidence', 0)
    
    return f'''
    <section class="code-validation-section">
        <h2>3. Code Validation</h2>
        <p>Analysis of {total_snippets} code snippet(s) found in the document.</p>
        
        <div class="code-summary">
            <div class="code-summary-grid">
                <div class="code-stat">
                    <div class="code-stat-value">{total_snippets}</div>
                    <div class="code-stat-label">Total Snippets</div>
                </div>
                <div class="code-stat">
                    <div class="code-stat-value">{valid_count}</div>
                    <div class="code-stat-label">Valid</div>
                </div>
                <div class="code-stat">
                    <div class="code-stat-value">{invalid_count}</div>
                    <div class="code-stat-label">Invalid</div>
                </div>
                <div class="code-stat">
                    <div class="code-stat-value">{accuracy:.0f}%</div>
                    <div class="code-stat-label">Accuracy</div>
                </div>
            </div>
        </div>
        
        <div class="code-validations">
            {''.join(validation_items)}
        </div>
    </section>
    '''


def generate_section_validation_section(section_data: Dict[str, Any]) -> str:
    """Generate section validation section HTML."""
    if not section_data:
        return ''
    
    completeness_score = section_data.get('completeness_score', 0)
    missing_sections = section_data.get('missing_sections', [])
    present_sections = section_data.get('present_sections', [])
    details = section_data.get('details', {})
    total_required = details.get('total_required', 0)
    found_count = details.get('found_count', 0)
    
    # Generate present sections list
    present_html = ''
    if present_sections:
        present_items = ''.join([f'<li>{section}</li>' for section in present_sections])
        present_html = f'''
        <div class="section-list">
            <h3>Present Sections ({found_count})</h3>
            <ul class="section-items present">{present_items}</ul>
        </div>
        '''
    
    # Generate missing sections list
    missing_html = ''
    if missing_sections:
        missing_items = ''.join([f'<li>{section}</li>' for section in missing_sections])
        missing_html = f'''
        <div class="section-list">
            <h3>Missing Sections ({len(missing_sections)})</h3>
            <ul class="section-items missing">{missing_items}</ul>
        </div>
        '''
    
    # Determine status
    if completeness_score >= 100:
        status_text = 'COMPLETE'
        status_color = '#2e7d32'
    elif completeness_score >= 75:
        status_text = 'MOSTLY COMPLETE'
        status_color = '#f57c00'
    else:
        status_text = 'INCOMPLETE'
        status_color = '#d32f2f'
    
    return f'''
    <section class="section-validation-section">
        <h2>4. Section Validation</h2>
        <p>Document structure analysis showing required sections presence.</p>
        
        <div class="section-summary">
            <div class="section-score-container">
                <div class="section-score-circle">
                    <div class="section-score-value">{completeness_score:.0f}%</div>
                    <div class="section-score-label">Completeness</div>
                </div>
                <div class="section-status" style="color: {status_color};">
                    <strong>{status_text}</strong>
                </div>
            </div>
            <div class="section-stats">
                <div class="section-stat-item">
                    <span class="section-stat-label">Total Required:</span>
                    <span class="section-stat-value">{total_required}</span>
                </div>
                <div class="section-stat-item">
                    <span class="section-stat-label">Found:</span>
                    <span class="section-stat-value">{found_count}</span>
                </div>
                <div class="section-stat-item">
                    <span class="section-stat-label">Missing:</span>
                    <span class="section-stat-value">{len(missing_sections)}</span>
                </div>
            </div>
        </div>
        
        <div class="section-details">
            {present_html}
            {missing_html}
        </div>
    </section>
    '''





def generate_accessibility_section(accessibility_data: Dict[str, Any]) -> str:
    """Generate accessibility validation section HTML."""
    if not accessibility_data:
        return ''
        
    report = accessibility_data.get('report', {})
    if not report:
        # Fallback if structure is different or flattened
        report = accessibility_data
        
    score = report.get('accessibility_score', 0)
    is_compliant = report.get('is_compliant', False)
    issues = report.get('issues', [])
    
    status_text = 'COMPLIANT' if is_compliant else 'NON-COMPLIANT'
    status_color = '#2e7d32' if is_compliant else '#d32f2f'
    
    issues_html = ''
    if issues:
        issues_list = []
        for issue in issues:
            loc = issue.get('location', 'Unknown location')
            msg = issue.get('issue', 'Unknown issue')
            issues_list.append(f'<li><strong>{loc}:</strong> {msg}</li>')
        
        issues_html = f'''
        <div class="access-issues">
            <h3>Accessibility Issues ({len(issues)})</h3>
            <ul class="access-issue-list">{''.join(issues_list)}</ul>
        </div>
        '''
        
    return f'''
    <section class="accessibility-section">
        <h2>5. Accessibility Validation</h2>
        <div class="access-summary">
            <div class="access-score-container">
                <div class="access-score">
                    <span class="score-val">{score}</span>
                    <span class="score-max">/100</span>
                </div>
                <div class="access-status" style="color: {status_color};">
                    {status_text}
                </div>
            </div>
            {issues_html}
        </div>
    </section>
    '''


def generate_google_search_section(search_data: Dict[str, Any]) -> str:
    """Generate google search validation section HTML."""
    if not search_data:
        return ''
        
    results = []
    if isinstance(search_data, list):
        results = search_data
    else:
        results = search_data.get('results', [])
        
    if not results:
        return ''
        
    items_html = []
    for res in results:
        title = res.get('title', '')
        # Fallback if title is empty/missing but term exists (legacy support)
        if not title:
            title = res.get('term', '')

        error = res.get('error')
        
        if error:
            # Handle error case
            status_badge = 'ERROR'
            status_bg = '#d32f2f'
            error_msg = str(error)
            if "Quota exceeded" in error_msg:
                detail_msg = "Google Search Quota Exceeded"
            else:
                detail_msg = error_msg[:100] + "..." if len(error_msg) > 100 else error_msg
                
            items_html.append(f'''
            <div class="search-item">
                <div class="search-term">"{title}"</div>
                <div class="search-meta">
                    <span class="search-status" style="background: {status_bg};">{status_badge}</span>
                    <span class="search-conf" style="color: #d32f2f;">{detail_msg}</span>
                </div>
            </div>
            ''')
        else:
            # Found means it exists online -> Plagiarized/Not Unique
            found = res.get('found', False)
            
            if found:
                status_badge = 'FOUND'
                status_bg = '#d32f2f' # Red
                status_desc = 'Title found in Google Search Results'
            else:
                status_badge = 'NOT FOUND'
                status_bg = '#2e7d32' # Green
                status_desc = 'Title not found in Google Search'
            
            items_html.append(f'''
            <div class="search-item">
                <div class="search-term">"{title}"</div>
                <div class="search-meta">
                    <span class="search-status" style="background: {status_bg};">{status_badge}</span>
                    <span class="search-conf">{status_desc}</span>
                </div>
            </div>
            ''')
        
    return f'''
    <section class="google-search-section">
        <h2>6. Google Search Validation</h2>
        <p>Verified title uniqueness against external sources (Google Search).</p>
        <div class="search-results">
            {''.join(items_html)}
        </div>
    </section>
    '''


def generate_visual_validation_section(visual_data: Dict[str, Any]) -> str:
    """Generate visual validation section HTML."""
    if not visual_data:
        return ''
        
    # Assuming visual_data structure based on usage
    issues = []
    score = None
    
    if isinstance(visual_data, dict):
        issues = visual_data.get('issues', [])
        score = visual_data.get('score', None)
        # If dict is the issue list directly (unlikely based on views.py visual_validator logic)
        if not issues and not score and 'issues' not in visual_data:
             pass 
    elif isinstance(visual_data, list):
        issues = visual_data
        
    # Formatting
    issues_html = ''
    if issues:
        issues_list = []
        for issue in issues:
            desc = str(issue)
            issues_list.append(f'<li>{desc}</li>')
        issues_html = f'<ul class="visual-issues">{"".join(issues_list)}</ul>'
        
    score_html = ''
    if score is not None:
        score_html = f'<div class="visual-score">Visual Score: <strong>{score}</strong></div>'

    return f'''
    <section class="visual-section">
        <h2>7. Visual Validation</h2>
        {score_html}
        {issues_html or '<p>No visual issues detected. Document layout appears consistent.</p>'}
    </section>
    '''


def generate_title_validation_section(title_data: Any) -> str:
    """Generate title validation section HTML."""
    if not title_data:
        return ''
    
    title = "Unknown"
    is_valid = False
    
    if isinstance(title_data, str):
        title = title_data
        is_valid = True if title else False
    elif isinstance(title_data, dict):
        title = title_data.get('title', 'Unknown')
        is_valid = title_data.get('is_valid', False)
        
    status_color = '#2e7d32' if is_valid else '#d32f2f'
    
    return f'''
    <section class="title-section">
        <h2>8. Title Validation</h2>
        <div class="title-card" style="border-left: 4px solid {status_color}">
            <div class="title-content">
                <strong>Extracted Title:</strong>
                <p>{title}</p>
            </div>
            <div style="clear: both;"></div>
        </div>
    </section>
    '''


def generate_reference_validation_section(reference_data: Dict[str, Any]) -> str:
    """Generate reference validation section HTML."""
    if not reference_data:
        return ''
    
    # Check for new format with 'details' list
    if 'details' in reference_data and isinstance(reference_data['details'], list):
        total_refs = len(reference_data['details'])
        valid_timeline = sum(1 for r in reference_data['details'] if r.get('timeline_validation', {}).get('is_valid'))
        valid_format = sum(1 for r in reference_data['details'] if r.get('format_validation', {}).get('is_valid'))
        
        # Calculate an overall status simply
        if total_refs == 0:
            overall = "NO REFERENCES"
            color = "#666"
        elif valid_timeline == total_refs and valid_format == total_refs:
            overall = "PASSED"
            color = "#2e7d32"
        else:
            overall = "ATTENTION NEEDED"
            color = "#f57c00"

        details_html = []
        for idx, ref in enumerate(reference_data['details'], 1):
            raw_text = ref.get('raw_text', 'Unknown Reference')
            # Truncate if too long
            display_text = raw_text[:150] + "..." if len(raw_text) > 150 else raw_text
            
            timeline = ref.get('timeline_validation', {})
            fmt = ref.get('format_validation', {})
            
            t_valid = timeline.get('is_valid', False)
            t_msg = timeline.get('message', '')
            f_valid = fmt.get('is_valid', False)
            f_issues = fmt.get('issues', [])
            
            # Status badge
            ref_status = 'VALID' if t_valid and f_valid else 'ISSUE'
            ref_color = '#2e7d32' if t_valid and f_valid else '#d32f2f'
            
            issues_list = []
            if not t_valid:
                issues_list.append(f"Timeline: {t_msg}")
            if not f_valid:
                for issue in f_issues:
                    issues_list.append(f"Format: {issue}")
            
            issues_html = ''
            if issues_list:
                issues_html = f'<div style="color: #d32f2f; font-size: 0.9em; margin-top: 5px;"><strong>Issues:</strong> <br/>{"<br/>".join(issues_list)}</div>'

            details_html.append(f'''
            <div class="ref-item" style="margin-bottom: 12px; padding: 10px; background: #fff; border-left: 3px solid {ref_color}; border: 1px solid #eee;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                    <strong style="color: #333;">Reference [{idx}]</strong>
                    <span style="background: {ref_color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.8em;">{ref_status}</span>
                </div>
                <div style="font-style: italic; color: #555; font-size: 0.9em; margin-bottom: 5px;">"{display_text}"</div>
                {issues_html}
            </div>
            ''')
            
        return f'''
        <section class="reference-section">
            <h2>9. Reference/Constraint Validation</h2>
            <div class="ref-summary">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding: 10px; background: #f9f9f9;">
                    <span>Found <strong>{total_refs}</strong> references</span>
                    <strong style="color: {color};">{overall}</strong>
                </div>
                <div class="ref-details-list">
                    {''.join(details_html)}
                </div>
            </div>
        </section>
        '''

    # Fallback to old format
    overall = reference_data.get('overall_status', 'Unknown')
    checks = reference_data.get('checks', {})
    
    checks_html = []
    for check_name, check_data in checks.items():
        status = check_data.get('status', 'unknown')
        msg = check_data.get('message', '')
        
        icon = '✓' if status == 'passed' else '!'
        color = '#2e7d32' if status == 'passed' else '#f57c00'
        if status == 'failed': color = '#d32f2f'
        
        checks_html.append(f'''
        <div class="ref-check-item" style="margin-bottom: 10px; padding: 10px; background: #f9f9f9;">
            <strong style="color: {color};">{icon} {check_name.replace('_', ' ').title()}</strong>
            <p style="margin: 5px 0 0 20px; font-size: 0.9em;">{msg}</p>
        </div>
        ''')

    return f'''
    <section class="reference-section">
        <h2>9. Reference/Constraint Validation</h2>
        <div class="ref-summary">
            <p>Overall Status: <strong>{overall.upper()}</strong></p>
            <div class="ref-checks">
                {''.join(checks_html)}
            </div>
        </div>
    </section>
    '''


def generate_formatting_validation_section(fmt_data: Dict[str, Any]) -> str:
    """Generate formatting validation section HTML."""
    if not fmt_data:
        return ''
        
    fonts = fmt_data.get('fonts', {})   
    margins = fmt_data.get('margins', {})
    spacing = fmt_data.get('spacing', {})
    warnings = fmt_data.get('warnings', [])
    
    font_str = f"{fonts.get('primary', 'Unknown')} ({', '.join(map(str, fonts.get('values', [])))})"
    margin_str = f"Top: {margins.get('top')}, Bottom: {margins.get('bottom')}, L: {margins.get('left')}, R: {margins.get('right')} ({margins.get('units')})"
    
    warnings_html = ''
    if warnings:
        w_list = ''.join([f'<li>{w}</li>' for w in warnings])
        warnings_html = f'<div class="fmt-warnings"><strong>Warnings:</strong><ul>{w_list}</ul></div>'

    return f'''
    <section class="formatting-section">
        <h2>Formatting Analysis</h2>
        <div class="fmt-details">
            <p><strong>Fonts:</strong> {font_str}</p>
            <p><strong>Margins:</strong> {margin_str}</p>
            {warnings_html}
        </div>
    </section>
    '''

def get_report_styles() -> str:
    """Return CSS styles for the report - Professional A4 Document Format."""
    return '''
        @page {
            size: A4;
            margin: 2cm;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Times New Roman', Georgia, serif;
            background: #ffffff;
            color: #000000;
            line-height: 1.6;
            font-size: 12pt;
        }
        
        .container {
            max-width: 21cm;
            min-height: 29.7cm;
            margin: 0 auto;
            background: white;
            padding: 2cm;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        
        .report-header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 3px double #000;
        }
        
        .report-header h1 {
            font-size: 24pt;
            font-weight: bold;
            color: #000;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .timestamp {
            color: #666;
            font-size: 10pt;
            font-style: italic;
        }
        
        .health-score-container {
            margin: 20px 0;
            text-align: center;
            page-break-inside: avoid;
        }
        
        .score-circle {
            width: 120px;
            height: 120px;
            margin: 0 auto;
            border: 4px solid #000;
            border-radius: 50%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: #f5f5f5;
        }
        
        .score-value {
            font-size: 36pt;
            font-weight: bold;
            color: #000;
        }
        
        .score-label {
            font-size: 9pt;
            color: #333;
            font-weight: 600;
            text-transform: uppercase;
        }
        
        .executive-summary {
            margin-bottom: 30px;
            page-break-inside: avoid;
        }
        
        h2 {
            font-size: 16pt;
            margin: 25px 0 15px 0;
            color: #000;
            font-weight: bold;
            border-bottom: 2px solid #000;
            padding-bottom: 5px;
            text-transform: uppercase;
        }
        
        h3 {
            font-size: 13pt;
            margin: 15px 0 10px 0;
            color: #000;
            font-weight: bold;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
            margin: 20px 0;
            page-break-inside: avoid;
        }
        
        .stat-card {
            background: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 15px;
            text-align: center;
        }
        
        .stat-icon {
            font-size: 24pt;
            margin-bottom: 8px;
        }
        
        .stat-value {
            font-size: 20pt;
            font-weight: bold;
            color: #000;
            display: block;
            margin: 5px 0;
        }
        
        .stat-label {
            color: #666;
            font-size: 10pt;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .readability-section, .page-analysis-section, .math-validation-section {
            margin-bottom: 30px;
            page-break-inside: avoid;
        }
        
        .chart-container {
            background: #fafafa;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 20px;
            margin: 15px 0;
            page-break-inside: avoid;
        }
        
        .page-analysis {
            background: #ffffff;
            border: 1px solid #ccc;
            border-radius: 5px;
            padding: 20px;
            margin-bottom: 20px;
            page-break-inside: avoid;
        }
        
        .page-analysis h3 {
            color: #000;
            margin-bottom: 12px;
            font-size: 12pt;
        }
        
        .readability-metrics {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ddd;
            font-size: 10pt;
        }
        
        .metric {
            color: #333;
        }
        
        .metric strong {
            color: #000;
            font-weight: bold;
        }
        
        .errors-container {
            margin-top: 12px;
        }
        
        .error-item {
            background: #fff;
            border-left: 3px solid #d32f2f;
            padding: 12px;
            margin-bottom: 10px;
            font-size: 10pt;
        }
        
        .error-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
        }
        
        .error-icon {
            font-size: 11pt;
        }
        
        .error-type {
            font-weight: bold;
            font-size: 9pt;
            color: #d32f2f;
            margin-right: 8px;
        }
        
        .error-text {
            font-weight: bold;
            color: #d32f2f;
            font-family: 'Courier New', monospace;
        }
        
        .error-message {
            color: #333;
            font-size: 9pt;
            margin-left: 25px;
            line-height: 1.4;
        }
        
        .error-suggestion {
            color: #1976d2;
            font-size: 9pt;
            margin-left: 25px;
            margin-top: 4px;
            font-style: italic;
        }
        
        .no-errors {
            color: #2e7d32;
            text-align: center;
            padding: 15px;
            font-weight: bold;
        }
        
        .math-status {
            background: #f5f5f5;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 20px;
            margin-top: 15px;
            page-break-inside: avoid;
        }
        
        .status-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 12px;
        }
        
        .status-icon {
            font-size: 14pt;
        }
        
        .status-text {
            font-size: 11pt;
            font-weight: bold;
        }
        
        .status-message {
            color: #333;
            margin-bottom: 8px;
            font-size: 10pt;
        }
        
        .status-meta {
            color: #666;
            font-size: 9pt;
            font-style: italic;
        }
        
        .empty-state {
            text-align: center;
            padding: 60px 20px;
        }
        
        .empty-icon {
            font-size: 48pt;
            margin-bottom: 20px;
        }
        
        .empty-state h2 {
            color: #666;
            margin-bottom: 10px;
        }
        
        .empty-state p {
            color: #999;
        }
        
        .report-footer {
            text-align: center;
            margin-top: 40px;
            padding-top: 15px;
            border-top: 1px solid #ccc;
            color: #666;
            font-size: 9pt;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
            font-size: 10pt;
        }
        
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        
        th {
            background-color: #f2f2f2;
            font-weight: bold;
            text-transform: uppercase;
            font-size: 9pt;
        }
        
        .code-validation-section {
            margin-bottom: 30px;
            page-break-inside: avoid;
        }
        
        .code-summary {
            background: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 20px;
            margin: 15px 0;
        }
        
        .code-summary-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
        }
        
        .code-stat {
            text-align: center;
        }
        
        .code-stat-value {
            font-size: 18pt;
            font-weight: bold;
            color: #000;
            display: block;
            margin-bottom: 5px;
        }
        
        .code-stat-label {
            font-size: 9pt;
            color: #666;
            text-transform: uppercase;
        }
        
        .code-validations {
            margin-top: 20px;
        }
        
        .code-validation-item {
            background: #ffffff;
            border: 1px solid #ccc;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 20px;
            page-break-inside: avoid;
        }
        
        .code-header {
            display: flex;
            gap: 10px;
            align-items: center;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid #ddd;
            flex-wrap: wrap;
        }
        
        .code-number {
            font-weight: bold;
            font-size: 11pt;
            color: #000;
        }
        
        .code-location {
            color: #666;
            font-size: 9pt;
            font-style: italic;
        }
        
        .code-language {
            background: #e0e0e0;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 8pt;
            font-weight: bold;
            color: #333;
        }
        
        .code-status {
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 8pt;
            font-weight: bold;
            color: white;
            margin-left: auto;
        }
        
        .code-snippet {
            background: #f5f5f5;
            border: 1px solid #ddd;
            border-left: 3px solid #333;
            padding: 12px;
            margin: 10px 0;
            overflow-x: auto;
            font-family: 'Courier New', monospace;
            font-size: 9pt;
            line-height: 1.4;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .code-snippet code {
            font-family: 'Courier New', monospace;
            color: #000;
        }
        
        .code-analysis {
            margin-top: 12px;
            font-size: 10pt;
        }
        
        .code-confidence {
            margin-bottom: 8px;
            color: #333;
        }
        
        .code-reasoning {
            margin-bottom: 12px;
            padding: 10px;
            background: #fafafa;
            border-left: 3px solid #666;
            font-size: 9pt;
            line-height: 1.5;
        }
        
        .code-issues {
            margin-top: 10px;
            padding: 10px;
            background: #fff5f5;
            border-left: 3px solid #d32f2f;
            font-size: 9pt;
        }
        
        .code-issues strong {
            color: #d32f2f;
            display: block;
            margin-bottom: 5px;
        }
        
        .code-issues ul {
            margin-left: 20px;
            margin-top: 5px;
        }
        
        .code-issues li {
            margin-bottom: 3px;
            color: #333;
        }
        
        .code-suggestions {
            margin-top: 10px;
            padding: 10px;
            background: #f0f7ff;
            border-left: 3px solid #1976d2;
            font-size: 9pt;
        }
        
        .code-suggestions strong {
            color: #1976d2;
            display: block;
            margin-bottom: 5px;
        }
        
        .code-suggestions ul {
            margin-left: 20px;
            margin-top: 5px;
        }
        
        .code-suggestions li {
            margin-bottom: 3px;
            color: #333;
        }
        
        .section-validation-section {
            margin-bottom: 30px;
            page-break-inside: avoid;
        }
        
        .section-summary {
            background: #f9f9f9;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 20px;
            margin: 15px 0;
        }
        
        .section-score-container {
            display: flex;
            align-items: center;
            gap: 30px;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid #ddd;
        }
        
        .section-score-circle {
            width: 100px;
            height: 100px;
            border: 3px solid #000;
            border-radius: 50%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            background: #fff;
        }
        
        .section-score-value {
            font-size: 24pt;
            font-weight: bold;
            color: #000;
        }
        
        .section-score-label {
            font-size: 8pt;
            color: #666;
            text-transform: uppercase;
        }
        
        .section-status {
            font-size: 14pt;
            font-weight: bold;
        }
        
        .section-stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
        }
        
        .section-stat-item {
            display: flex;
            justify-content: space-between;
            padding: 8px;
            background: #fff;
            border-radius: 3px;
        }
        
        .section-stat-label {
            color: #666;
            font-size: 9pt;
        }
        
        .section-stat-value {
            font-weight: bold;
            color: #000;
            font-size: 10pt;
        }
        
        .section-details {
            margin-top: 20px;
        }
        
        .section-list {
            margin-bottom: 20px;
        }
        
        .section-list h3 {
            font-size: 11pt;
            margin-bottom: 10px;
            color: #000;
        }
        
        .section-items {
            list-style: none;
            padding: 0;
            margin: 0;
        }
        
        .section-items li {
            padding: 8px 12px;
            margin-bottom: 5px;
            border-radius: 3px;
            font-size: 10pt;
        }
        
        .section-items.present li {
            background: #e8f5e9;
            border-left: 3px solid #2e7d32;
            color: #1b5e20;
        }
        
        .section-items.missing li {
            background: #ffebee;
            border-left: 3px solid #d32f2f;
            color: #b71c1c;
        }
        
        @media print {
            body {
                background: white;
            }
            .container {
                box-shadow: none;
                margin: 0;
                padding: 0;
            }
            .page-analysis, .math-status, .chart-container {
                page-break-inside: avoid;
            }
            h2 {
                page-break-after: avoid;
            }
        }
        
        @media screen {
            body {
                background: #e0e0e0;
                padding: 20px;
            }
        }
    '''


def get_report_scripts() -> str:
    """Return JavaScript for the report."""
    return '''
        // Chart.js CDN
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js';
        document.head.appendChild(script);
        
        // Smooth scroll
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth' });
                }
            });
        });
    '''
