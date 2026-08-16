import sys
import os
import re
import json
import pdfplumber

def parse_uspf_evaluation(pdf_source):
    try:
        # pdfplumber.open accepts file paths, BytesIO, or file objects
        if isinstance(pdf_source, str) and not os.path.exists(pdf_source):
            return {'error': f'File not found: {pdf_source}'}

        with pdfplumber.open(pdf_source) as pdf:
            if len(pdf.pages) == 0:
                return {'error': 'PDF document has no pages.'}
            page = pdf.pages[0]
            words = page.extract_words()
            page_width = page.width

            full_text = page.extract_text() or ''

            # Validate USPF PDF Document
            if not re.search(r'University\s+Of\s+Southern\s+Philippines\s+Foundation|USPF', full_text, re.IGNORECASE):
                return {'error': 'The uploaded PDF is not a valid USPF Evaluation Record.'}

            student_no_match = re.search(r'Student No:\s*(\d+)', full_text)
            student_name_match = re.search(r'Student Name:\s*([^\-]+)', full_text)
            curr_year_match = re.search(r'Curriculum Year\s*([\d\-]+)', full_text)
            year_admitted_match = re.search(r'Year Admitted:\s*([\d\-]+)', full_text)

            # Program extraction (e.g., "BSIT - Bachelor of Science in Information Technology", "BSN - Bachelor of Science in Nursing", etc.)
            program_match = re.search(r'\b([A-Z]{2,6}\s*[\-\–]\s*Bachelor.+?)(?=\s+Curriculum|\s+Student|\s+Year|\r|\n|$)', full_text, re.IGNORECASE)
            if not program_match:
                program_match = re.search(r'\b([A-Z]{2,6}\s*[\-\–]\s*.+?)(?=\s+Curriculum|\s+Student|\s+Year|\r|\n|$)', full_text)

            program_str = program_match.group(1).strip() if program_match else 'USPF 4-Year Degree Program'

            student_info = {
                'student_no': student_no_match.group(1) if student_no_match else '',
                'student_name': student_name_match.group(1).strip() if student_name_match else '',
                'program': program_str,
                'curriculum_year': curr_year_match.group(1) if curr_year_match else '',
                'year_admitted': year_admitted_match.group(1) if year_admitted_match else ''
            }

            # Group words by vertical y coordinate (top)
            lines = {}
            for w in words:
                found = False
                for k in lines:
                    if abs(k - w['top']) < 3.5:
                        lines[k].append(w)
                        found = True
                        break
                if not found:
                    lines[w['top']] = [w]

            left_lines = []
            right_lines = []

            for k in sorted(lines.keys()):
                line_words = sorted(lines[k], key=lambda x: x['x0'])
                l_words = [w['text'] for w in line_words if w['x0'] < page_width / 2]
                r_words = [w['text'] for w in line_words if w['x0'] >= page_width / 2]

                l_str = ' '.join(l_words).strip()
                r_str = ' '.join(r_words).strip()

                if l_str:
                    left_lines.append(l_str)
                if r_str:
                    right_lines.append(r_str)

        # Structure for 4 years x 2 sem
        parsed_data = {
            'student': student_info,
            'years': { str(y): { '1': [], '2': [] } for y in range(1, 5) }
        }

        prog_prefix = program_str.split('-')[0].strip() if '-' in program_str else ''

        def process_side(lines_list, sem_num):
            active_year = 1
            current_subj = None

            for line in lines_list:
                # Filter headers, legends, program degree title, and noise
                if any(hdr in line for hdr in ['University Of Southern', 'Salinas Drive', 'Curriculum Year', 'Student No:', 'Total credited', 'Total No.', 'Legend:', 'Printed By', '================']):
                    continue
                if 'Bachelor' in line or (prog_prefix and line.startswith(prog_prefix)):
                    continue

                # Year-separator lines like "this is the correct subject 26" —
                # they may embed a unit total that signals a year transition.
                if 'this is the correct subject' in line:
                    trailing_num = re.search(r'(\d+(?:\.\d+)?)\s*$', line)
                    if trailing_num:
                        active_year = min(active_year + 1, 4)
                        current_subj = None
                    continue

                if line.startswith('FS -') or line.startswith('SS -') or line.startswith('SU -') or line.startswith('T -'):
                    continue
                
                # Check for standalone sum numbers like 24.5, 44.5, 62.5, 77.5, 26, 46, 64, 73
                if re.match(r'^\d+(?:\.\d+)?$', line.strip()):
                    active_year = min(active_year + 1, 4)
                    current_subj = None
                    continue

                # Matches subject lines across any USPF 4-year department:
                # m1: "1.2 FS23-24 CC111 Introduction to Computing 3"
                m1 = re.match(r'^(\d\.\d)\s+(?:([FSSU]{2}\d{2}\-\d{2})\s+)?([A-Z]{2,6}\s*[\d\-]*[A-Z0-9]*)\s+(.+?)\s+(\d+(?:\.\d+)?)$', line)
                # m2: "_______ PE2-FE Fitness Exercises 2" or "_______ FIL221..."
                m2 = re.match(r'^_______\s+(?:([FSSU]{2}\d{2}\-\d{2})\s+)?([A-Z]{2,6}\s*[\d\-]*[A-Z0-9]*)\s+(.+?)\s+(\d+(?:\.\d+)?)$', line)
                # m3: "FS26-27 IT411 Information Assurance & Security 2 3" or "CC111 Introduction to Computing 3"
                m3 = re.match(r'^(?:([FSSU]{2}\d{2}\-\d{2})\s+)?([A-Z]{2,6}\s*[\d\-]*[A-Z0-9]*)\s+(.+?)\s+(\d+(?:\.\d+)?)$', line)

                m = m1 or m2 or m3
                if m:
                    if m1:
                        grade_val = float(m1.group(1))
                        term_str = m1.group(2) or ''
                        code_str = m1.group(3).strip()
                        title_str = m1.group(4).strip()
                        units_val = float(m1.group(5))
                    elif m2:
                        grade_val = None
                        term_str = m2.group(1) or ''
                        code_str = m2.group(2).strip()
                        title_str = m2.group(3).strip()
                        units_val = float(m2.group(4))
                    else: # m3
                        grade_val = None
                        term_str = m3.group(1) or ''
                        code_str = m3.group(2).strip()
                        title_str = m3.group(3).strip()
                        units_val = float(m3.group(4))

                    if term_str:
                        if '23-24' in term_str: active_year = 1
                        elif '24-25' in term_str: active_year = 2
                        elif '25-26' in term_str: active_year = 3
                        elif '26-27' in term_str: active_year = 4

                    is_pe_nstp = bool(re.search(r'\b(PE\d*|NSTP\d*|SOCOR)\b', f'{code_str} {title_str}', re.I))

                    subj_obj = {
                        'code': code_str,
                        'title': title_str,
                        'name': f'{code_str} - {title_str}',
                        'units': units_val,
                        'grade': grade_val,
                        'term': term_str,
                        'isPENSTP': is_pe_nstp
                    }
                    parsed_data['years'][str(active_year)][str(sem_num)].append(subj_obj)
                    current_subj = subj_obj
                else:
                    if current_subj and line.strip() and not line.startswith('this is'):
                        current_subj['title'] += ' ' + line.strip()
                        current_subj['name'] = f"{current_subj['code']} - {current_subj['title']}"

        process_side(left_lines, 1)
        process_side(right_lines, 2)

        return parsed_data

    except Exception as e:
        return {'error': str(e)}

if __name__ == '__main__':
    if len(sys.argv) < 2:
        file_path = 'evaluation_of_student.pdf'
    else:
        file_path = sys.argv[1]

    result = parse_uspf_evaluation(file_path)
    print(json.dumps(result, indent=2))
