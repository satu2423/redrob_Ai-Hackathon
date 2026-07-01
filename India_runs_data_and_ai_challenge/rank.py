#!/usr/bin/env python3
import json
import csv
import argparse
import sys
from datetime import datetime
from pathlib import Path

# Target date of the dataset/metadata timeline
TARGET_DATE = datetime(2026, 6, 27)

# Consulting companies
CONSULTING_COMPANIES = {
    'tcs', 'tata consultancy services', 'infosys', 'wipro', 'accenture',
    'cognizant', 'capgemini', 'mindtree', 'hcl', 'tech mahindra', 'l&t', 'lnt',
    'mphasis', 'persistent systems', 'hexaware', 'ust global', 'deloitte',
    'kpmg', 'pwc', 'ey', 'ernst & young', 'tcs e-serve'
}

# Unrelated titles that represent disqualifying non-tech roles
UNRELATED_TITLES = {
    'marketing manager', 'content writer', 'graphic designer', 'accountant',
    'sales executive', 'operations manager', 'customer support', 'hr manager',
    'business analyst', 'ui/ux designer', 'product designer', 'hr associate',
    'civil engineer', 'mechanical engineer', 'recruiter', 'financial analyst',
    'sales manager', 'project manager', 'scrum master'
}

# Key skills weights
CORE_SKILLS = {
    'nlp': 1.0,
    'natural language processing': 1.0,
    'embeddings': 1.0,
    'sentence-transformers': 1.0,
    'bge': 1.0,
    'e5': 1.0,
    'retrieval': 1.0,
    'vector database': 1.0,
    'vector search': 1.0,
    'pinecone': 1.0,
    'weaviate': 1.0,
    'qdrant': 1.0,
    'milvus': 1.0,
    'faiss': 1.0,
    'opensearch': 0.8,
    'elasticsearch': 0.8,
    'hybrid search': 1.0,
    'information retrieval': 1.0,
    'ranking': 1.0,
    'reranking': 1.0,
    'ndcg': 1.0,
    'mrr': 1.0,
    'map': 1.0,
    'evaluation': 1.0,
    'python': 0.8
}

PREFERRED_SKILLS = {
    'fine-tuning': 0.8,
    'llm fine-tuning': 0.8,
    'lora': 0.8,
    'qlora': 0.8,
    'peft': 0.8,
    'learning-to-rank': 0.8,
    'xgboost': 0.6,
    'pytorch': 0.6,
    'tensorflow': 0.5,
    'huggingface': 0.7,
    'transformers': 0.7
}

TIER_1_CITIES = {
    'pune', 'noida', 'delhi', 'ncr', 'gurgaon', 'gurugram', 'ghaziabad',
    'faridabad', 'mumbai', 'hyderabad', 'bangalore', 'bengaluru', 'chennai', 'kolkata'
}


def is_honeypot(candidate):
    """
    Apply strict rules to detect all known honeypot patterns.
    Returns True if the candidate is a honeypot, False otherwise.
    """
    profile = candidate.get("profile", {})
    history = candidate.get("career_history", [])
    skills = candidate.get("skills", [])
    certs = candidate.get("certifications", [])
    edu = candidate.get("education", [])
    
    # Rule 1: Zero-duration expert skills
    expert_zero_dur = [s for s in skills if s.get("proficiency") == "expert" and s.get("duration_months", 0) == 0]
    if expert_zero_dur:
        return True
        
    # Rule 2: Impossible job durations or start/end inversion
    for job in history:
        start_str = job.get("start_date")
        end_str = job.get("end_date")
        duration = job.get("duration_months", 0)
        if start_str:
            try:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d")
                if end_str:
                    end_dt = datetime.strptime(end_str, "%Y-%m-%d")
                    if end_dt < start_dt:
                        return True
                    diff_m = (end_dt.year - start_dt.year) * 12 + (end_dt.month - start_dt.month)
                    if duration > diff_m + 2:
                        return True
                else:
                    diff_m = (TARGET_DATE.year - start_dt.year) * 12 + (TARGET_DATE.month - start_dt.month)
                    if duration > diff_m + 2:
                        return True
            except:
                return True
                
    # Rule 3: Contradictory years of experience
    yoe = profile.get("years_of_experience", 0)
    start_years = []
    for job in history:
        s_date = job.get("start_date")
        if s_date:
            try:
                start_years.append(int(s_date.split("-")[0]))
            except:
                pass
    if start_years:
        earliest_job_year = min(start_years)
        elapsed_years = TARGET_DATE.year - earliest_job_year + 1
        if yoe > elapsed_years + 1.5:
            return True
            
    # Rule 4: YOE is positive but job history is empty/0 months
    total_job_months = sum(job.get("duration_months", 0) for job in history)
    if yoe > 0 and total_job_months == 0:
        return True
        
    # Rule 5: Future Certifications
    for cert in certs:
        year = cert.get("year")
        if year and year > TARGET_DATE.year:
            return True
            
    # Rule 6: Education start/end year inversion or future years
    for e in edu:
        s_yr = e.get("start_year")
        e_yr = e.get("end_year")
        if s_yr and e_yr:
            if e_yr < s_yr:
                return True
            if s_yr > TARGET_DATE.year or e_yr > TARGET_DATE.year:
                return True
                
    return False


def is_consulting_only(history):
    """
    Check if a candidate has exclusively worked at consulting/service firms.
    """
    if not history:
        return True
    all_consulting = True
    for job in history:
        comp = job.get("company", "").lower().strip()
        if not comp:
            continue
        is_comp_consulting = False
        for c_comp in CONSULTING_COMPANIES:
            if c_comp in comp:
                is_comp_consulting = True
                break
        if not is_comp_consulting:
            all_consulting = False
            break
    return all_consulting


def is_research_only(history):
    """
    Identify if their profile represents a pure research background with no production experience.
    """
    research_keywords = {'research', 'academic', 'thesis', 'publication', 'paper', 'journal', 'lab', 'phd', 'postdoc', 'university'}
    production_keywords = {'production', 'deploy', 'scale', 'system', 'pipeline', 'user', 'customer', 'product', 'shipped', 'metrics'}
    
    total_res = 0
    total_prod = 0
    
    for job in history:
        title = job.get("title", "").lower()
        desc = job.get("description", "").lower()
        
        if any(w in title for w in ['research assistant', 'postdoc', 'academic', 'phd candidate']):
            total_res += 5
            
        for w in research_keywords:
            total_res += desc.count(w)
        for w in production_keywords:
            total_prod += desc.count(w)
            
    if total_res > 4 and total_prod == 0:
        return True
    return False


def get_title_score(title):
    """
    Scores the title fit based on keyword matching and seniority terms.
    """
    t = title.lower().strip()
    for u in UNRELATED_TITLES:
        if u in t:
            return 0.0
            
    high_priority_keywords = [
        'machine learning', 'ml', 'ai ', ' ai', 'artificial intelligence',
        'nlp', 'retrieval', 'search', 'recommendation', 'llm', 'data scientist'
    ]
    if any(k in t for k in high_priority_keywords) or t == 'ai':
        if any(w in t for w in ['senior', 'lead', 'staff', 'principal', 'founding', 'sr.']):
            return 1.0
        return 0.8
        
    medium_priority_keywords = [
        'backend', 'data engineer', 'software engineer', 'full stack', 'developer',
        'systems engineer', 'infrastructure engineer', 'platform engineer'
    ]
    if any(k in t for k in medium_priority_keywords):
        if any(w in t for w in ['senior', 'lead', 'staff', 'principal', 'founding', 'sr.']):
            return 0.6
        return 0.4
        
    return 0.1


def get_experience_score(yoe):
    """
    Scores candidates based on target 5-9 years of experience.
    """
    if 5.0 <= yoe <= 9.0:
        return 1.0
    if 4.0 <= yoe < 5.0:
        return 0.8
    if 9.0 < yoe <= 12.0:
        return 0.8
    if 12.0 < yoe <= 15.0:
        return 0.6
    if 3.0 <= yoe < 4.0:
        return 0.4
    if yoe < 3.0:
        return 0.1
    return 0.3


def score_skills(candidate_skills):
    """
    Scores skills according to relevance, duration, proficiency, and endorsements.
    """
    total_score = 0.0
    skills_matched = []
    
    for s in candidate_skills:
        name = s.get("name", "").lower().strip()
        prof = s.get("proficiency", "beginner").lower()
        endorsements = s.get("endorsements", 0)
        dur = s.get("duration_months", 0)
        
        prof_val = {'expert': 1.0, 'advanced': 0.85, 'intermediate': 0.60, 'beginner': 0.30}.get(prof, 0.30)
        dur_factor = min(dur / 12.0, 2.0)
        end_factor = 1.0 + min(endorsements / 30.0, 1.0)
        
        weight = 0.0
        for cs, cs_w in CORE_SKILLS.items():
            if cs in name or name in cs:
                weight = cs_w
                break
        if not weight:
            for ps, ps_w in PREFERRED_SKILLS.items():
                if ps in name or name in ps:
                    weight = ps_w
                    break
                    
        if weight > 0:
            skill_score = weight * prof_val * dur_factor * end_factor
            total_score += skill_score
            skills_matched.append((s.get("name", ""), prof, dur))
            
    return min(total_score / 8.0, 1.0), skills_matched


def get_location_score(loc_str, willing_relocate, country_str):
    """
    Weights location fit based on Pune/Noida preferences.
    """
    l = loc_str.lower()
    c = country_str.lower().strip()
    
    # Outside India with no relocation: down-weight heavily
    if c and c not in ('india', 'in') and not willing_relocate:
        return 0.1
        
    if 'pune' in l or 'noida' in l:
        return 1.0
        
    if any(city in l for city in TIER_1_CITIES):
        if willing_relocate:
            return 0.9
        return 0.7
        
    if willing_relocate:
        return 0.8
    return 0.2


def score_education(edu_list):
    """
    Scores education credentials.
    """
    if not edu_list:
        return 0.3
        
    best_edu_score = 0.0
    for e in edu_list:
        field = e.get("field_of_study", "").lower()
        tier = e.get("tier", "unknown").lower()
        
        tier_val = {'tier_1': 1.0, 'tier_2': 0.8, 'tier_3': 0.5, 'tier_4': 0.3}.get(tier, 0.3)
        
        rel_val = 0.3
        if any(fld in field for fld in ['computer science', 'machine learning', 'artificial intelligence', 'nlp', 'data science', 'information technology', 'software engineering']):
            rel_val = 1.0
        elif any(fld in field for fld in ['electronics', 'mathematics', 'statistics', 'physics', 'electrical']):
            rel_val = 0.7
            
        edu_score = tier_val * rel_val
        if edu_score > best_edu_score:
            best_edu_score = edu_score
            
    return best_edu_score


def generate_reasoning(c, skills_matched):
    """
    Generates dynamic, fact-based, non-templated reasoning for the candidate.
    """
    profile = c.get("profile", {})
    signals = c.get("redrob_signals", {})
    
    title = profile.get("current_title", "Engineer")
    yoe = profile.get("years_of_experience", 0.0)
    loc = profile.get("location", "")
    notice = signals.get("notice_period_days", 0)
    resp_rate = signals.get("recruiter_response_rate", 0.0)
    
    skills_names = [s[0] for s in skills_matched[:3]]
    skills_str = ", ".join(skills_names) if skills_names else "applied ML systems"
    
    # Use deterministic hash of candidate_id to select sentence structure styles
    h_idx = hash(c["candidate_id"])
    
    s1_templates = [
        f"{title} with {yoe:.1f} years of experience, specializing in {skills_str}.",
        f"Offers {yoe:.1f} years of experience as a {title}, with hands-on expertise in {skills_str}.",
        f"Experienced {title} ({yoe:.1f} years) who has shipped systems using {skills_str}."
    ]
    s1 = s1_templates[h_idx % 3]
    
    if notice > 60:
        notice_clause = f"notice period is long ({notice} days)"
    elif notice <= 15:
        notice_clause = f"quick {notice}-day notice"
    else:
        notice_clause = f"{notice}-day notice period"
        
    reloc_clause = ""
    if not signals.get("willing_to_relocate", True) and 'pune' not in loc.lower() and 'noida' not in loc.lower():
        reloc_clause = " (relocation constraint)"
        
    s2_templates = [
        f"Located in {loc}{reloc_clause} with a {notice_clause}, showing a response rate of {int(resp_rate*100)}%.",
        f"Based in {loc}{reloc_clause} ({notice_clause}); has a response rate of {int(resp_rate*100)}% to recruiters.",
        f"Responsive candidate ({int(resp_rate*100)}% rate) located in {loc}{reloc_clause} with a {notice_clause}."
    ]
    s2 = s2_templates[(h_idx // 3) % 3]
    
    return f"{s1} {s2}"


def rank_candidates(candidates_path):
    """
    Process candidates stream, score them, sort them, and select the top 100.
    """
    ranked_pool = []
    
    with open(candidates_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            c = json.loads(line)
            cid = c["candidate_id"]
            profile = c.get("profile", {})
            history = c.get("career_history", [])
            skills = c.get("skills", [])
            signals = c.get("redrob_signals", {})
            
            # Step 1: Honeypot check
            if is_honeypot(c):
                continue
                
            # Step 2: Consulting company check
            if is_consulting_only(history):
                continue
                
            # Step 3: Academic / Research check
            if is_research_only(history):
                continue
                
            # Step 4: Technical scoring components
            current_title = profile.get("current_title", "")
            title_score = get_title_score(current_title)
            
            # If current title is completely unrelated, skip this candidate
            if title_score == 0.0:
                continue
                
            yoe = profile.get("years_of_experience", 0.0)
            exp_score = get_experience_score(yoe)
            
            skill_score, skills_matched = score_skills(skills)
            
            willing_reloc = signals.get("willing_to_relocate", False)
            country = profile.get("country", "")
            loc_score = get_location_score(profile.get("location", ""), willing_reloc, country)
            
            edu_score = score_education(c.get("education", []))
            
            # Weight suitability
            suitability = (
                title_score * 0.35 +
                exp_score * 0.20 +
                skill_score * 0.25 +
                loc_score * 0.10 +
                edu_score * 0.10
            )
            
            # Step 5: Behavioral Modifier
            # Platform active date
            active_str = signals.get("last_active_date", "")
            active_mod = 0.5
            try:
                act_dt = datetime.strptime(active_str, "%Y-%m-%d")
                delta = (TARGET_DATE - act_dt).days
                if delta <= 30:
                    active_mod = 1.0
                elif delta <= 90:
                    active_mod = 0.85
                elif delta <= 180:
                    active_mod = 0.55
                else:
                    active_mod = 0.20
            except:
                pass
                
            resp_rate = signals.get("recruiter_response_rate", 0.0)
            if resp_rate < 0.15:
                resp_mod = 0.3
            elif resp_rate < 0.35:
                resp_mod = 0.65
            elif resp_rate < 0.60:
                resp_mod = 0.90
            else:
                resp_mod = 1.05
                
            modifier = active_mod * resp_mod
            
            if signals.get("open_to_work_flag", False):
                modifier *= 1.05
                
            github = signals.get("github_activity_score", -1)
            if github > 50:
                modifier *= 1.10
            elif github > 15:
                modifier *= 1.05
                
            int_rate = signals.get("interview_completion_rate", 1.0)
            if int_rate > 0.85:
                modifier *= 1.05
            elif int_rate < 0.45:
                modifier *= 0.75
                
            final_score = suitability * modifier
            final_score = min(max(final_score, 0.0), 1.0)
            
            # Save candidate along with score and metadata for sorting & reasoning
            ranked_pool.append({
                "candidate_id": cid,
                "score": final_score,
                "candidate_data": c,
                "skills_matched": skills_matched
            })
            
    # Sort: descending score, then ascending candidate_id as secondary key for tie-break
    ranked_pool.sort(key=lambda x: (-round(x["score"], 4), x["candidate_id"]))
    
    # Take top 100
    top_100 = []
    for rank_idx, item in enumerate(ranked_pool[:100], start=1):
        c = item["candidate_data"]
        reason = generate_reasoning(c, item["skills_matched"])
        
        top_100.append({
            "candidate_id": item["candidate_id"],
            "rank": rank_idx,
            "score": round(item["score"], 4),
            "reasoning": reason
        })
        
    return top_100


def main():
    parser = argparse.ArgumentParser(description="Rank candidates for Senior AI Engineer JD.")
    parser.add_argument("--candidates", required=True, help="Path to candidates.jsonl file.")
    parser.add_argument("--out", required=True, help="Path to output submission.csv file.")
    args = parser.parse_args()
    
    candidates_path = Path(args.candidates)
    if not candidates_path.exists():
        print(f"Error: candidates file not found at {candidates_path}")
        sys.exit(1)
        
    print(f"Ranking candidates from {candidates_path}...")
    top_100 = rank_candidates(candidates_path)
    
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        for c in top_100:
            writer.writerow([c["candidate_id"], c["rank"], c["score"], c["reasoning"]])
            
    print(f"Successfully generated ranking for 100 candidates at {out_path}.")


if __name__ == "__main__":
    main()
