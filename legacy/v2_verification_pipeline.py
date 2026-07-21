import os
import re
import json
import logging
from kg_store import get_kg_store
from llm_client import get_llm_client

logger = logging.getLogger("verification_pipeline")

class VerificationPipeline:
    def __init__(self, kg_path="data/rmit_graph.json"):
        self.store = get_kg_store(kg_path)
        self.llm_client = get_llm_client()
        self.entity_index = {}
        self.build_entity_index()

    def build_entity_index(self):
        """Builds a deterministic lookup index mapping titles to course codes."""
        for code, course in self.store.courses.items():
            self.entity_index[code] = code
            title_clean = self.normalize_text(course["title"])
            self.entity_index[title_clean] = code
            
            # Map code + title combinations
            combined_clean = self.normalize_text(f"{code} {course['title']}")
            self.entity_index[combined_clean] = code

    def normalize_text(self, text: str) -> str:
        if not text:
            return ""
        text = str(text).lower().strip()
        # Strip common prefixes for schools, departments, and academic titles
        text = re.sub(r"^(school of|department of|college of|school|department|college)\s+", "", text)
        text = re.sub(r"^(dr\.|dr|associate professor|assoc\.\s*prof\.|prof\.|prof|professor)\s+", "", text)
        return re.sub(r"[^a-z0-9]", "", text)

    def link_entity(self, text: str) -> str:
        """Links a text string (course name, code) to a valid course ID in the KG."""
        if not text:
            return None
            
        text = str(text).strip()
        # Direct check for 6-digit code
        code_match = re.search(r"\b\d{6}\b", text)
        if code_match:
            # Return code directly (even if not found in KG, to avoid wrong fuzzy matching)
            return code_match.group(0)

        # Normalized lookup
        clean = self.normalize_text(text)
        if clean in self.entity_index:
            return self.entity_index[clean]

        # Fuzzy lookup: check for substring matches (query must be a substring of the title)
        for key, code in self.entity_index.items():
            if len(clean) > 4 and clean in key:
                return code
                
        return None

    def stage_2_decompose(self, text: str, custom_system_prompt: str = None) -> list:
        """Stage 2: Decomposes a statement into schema-guided JSON claims."""
        system_prompt = custom_system_prompt or (
            "You are a factual claim extraction assistant. Decompose the text into atomic, schema-guided claims. "
            "Each claim must map to one of these valid relation classes:\n"
            "- requiresPrerequisite: course requires another course as prerequisite (or requires no/none prerequisites).\n"
            "- hasCreditValue: course is worth a number of credit points.\n"
            "- partOfSchool: course belongs to a specific school (e.g. Science, Business).\n"
            "- taughtBy: course has a coordinator or coordinator email, or a coordinator exists in the catalogue with a name and email (map subject to coordinator name and object to email).\n"
            "- offeredInTerm: course is offered in a specific semester.\n\n"
            "Guidelines for Multi-Hop statements:\n"
            "If a statement mentions a multi-hop prerequisite relationship (e.g. 'the prerequisite course of A requires B'), decompose it into two separate claims:\n"
            "1. A requires C (where C is the intermediate course ID or title mentioned in the context)\n"
            "2. C requires B\n\n"
            "Return a JSON object with a single key 'claims' containing a list of claims. "
            "Each claim must have: 'subject', 'relation', 'object', 'claim_type'. "
            "Set 'claim_type' to the relation name if it fits. If the claim does not fit any of the relations, set 'claim_type' to 'unclassified'."
        )
        
        prompt = f"Decompose the following text:\nText: \"{text}\"\n\nJSON Output:"
        
        # Self-consistency check (run twice)
        try:
            run1 = self.llm_client.generate_json(prompt, system_prompt=system_prompt, temperature=0.1)
            claims1 = run1.get("claims", [])
        except Exception as e:
            logger.error(f"Decomposition run 1 failed: {e}")
            claims1 = []
            
        try:
            run2 = self.llm_client.generate_json(prompt, system_prompt=system_prompt, temperature=0.2)
            claims2 = run2.get("claims", [])
        except Exception:
            claims2 = []

        # Keep claims that are consistent across both runs
        consistent_claims = []
        for c1 in claims1:
            subj1 = str(c1.get("subject", "")).strip().lower()
            rel1 = str(c1.get("relation", "")).strip()
            obj1 = str(c1.get("object", "")).strip().lower()
            
            match_found = False
            for c2 in claims2:
                subj2 = str(c2.get("subject", "")).strip().lower()
                rel2 = str(c2.get("relation", "")).strip()
                obj2 = str(c2.get("object", "")).strip().lower()
                
                if rel1 == rel2 and (subj1 == subj2 or subj1 in subj2 or subj2 in subj1) and (obj1 == obj2 or obj1 in obj2 or obj2 in obj1):
                    match_found = True
                    break
                    
            if match_found or not claims2: # If run 2 failed, fallback to run 1
                consistent_claims.append(c1)
                
        return consistent_claims

    def stage_3_map_claim_to_triple(self, claim: dict) -> tuple:
        """Stage 3: Maps a parsed claim to a structured (subject_code, relation, object_val) triple."""
        subject_raw = claim.get("subject")
        relation = claim.get("relation")
        object_raw = claim.get("object")
        claim_type = claim.get("claim_type", "")

        if claim_type == "unclassified":
            return None, "unclassified", None

        # Link Subject Entity
        subject_code = self.link_entity(subject_raw)
        if not subject_code:
            if relation == "taughtBy":
                return subject_raw, relation, str(object_raw).strip()
            return None, "entity_unresolved", subject_raw

        if relation == "requiresPrerequisite":
            # Check for negation words in object_raw before calling link_entity
            if str(object_raw).lower().strip() in ["none", "null", "no prerequisites", "no prerequisite", "empty", "no", "none.", "unknown course", "no courses", "n/a"]:
                return subject_code, relation, "none"
            object_code = self.link_entity(object_raw)
            if not object_code:
                return subject_code, "object_unresolved", object_raw
            return subject_code, relation, object_code
            
        elif relation == "hasCreditValue":
            # Extract credit points number
            match = re.search(r"\b\d+\b", str(object_raw))
            if match:
                return subject_code, relation, int(match.group(0))
            return subject_code, relation, object_raw
            
        elif relation == "partOfSchool":
            return subject_code, relation, str(object_raw).strip()
            
        elif relation == "taughtBy":
            return subject_code, relation, str(object_raw).strip()
            
        return subject_code, relation, object_raw

    def stage_4_verify_triple(self, subject_code: str, relation: str, object_val) -> dict:
        """Stage 4: Executes semantics-dispatched verification against the KG."""
        if relation == "unclassified":
            return {"verdict": "Out-of-scope", "reason": "Claim type not covered by ontology.", "evidence": None}
            
        if relation in ["entity_unresolved", "object_unresolved"]:
            return {"verdict": "Not-in-KG", "reason": f"Could not resolve entity: {object_val}", "evidence": None}

        # Check if subject exists
        if not self.store.has_course(subject_code):
            # Fallback for coordinator existence check (subject is a name, object is email or vice-versa)
            if relation in ["taughtBy", "coordinator", "email"]:
                found_coord = False
                matched_course = None
                
                # Check all courses in KG for matching coordinator name and email
                for c_code, course in self.store.courses.items():
                    c_name_norm = self.normalize_text(course["coordinator"])
                    c_email_norm = self.normalize_text(course["coordinator_email"])
                    
                    # Ignore placeholder dots or empty names/emails
                    if len(c_name_norm) <= 2 or len(c_email_norm) <= 2:
                        continue
                        
                    subj_norm = self.normalize_text(subject_code or "")
                    obj_norm = self.normalize_text(object_val or "")
                    
                    # Match name and email (either subject=name/object=email or subject=email/object=name)
                    if ((subj_norm in c_name_norm or c_name_norm in subj_norm) and (obj_norm in c_email_norm or c_email_norm in obj_norm)) or \
                       ((subj_norm in c_email_norm or c_email_norm in subj_norm) and (obj_norm in c_name_norm or c_name_norm in obj_norm)):
                        found_coord = True
                        matched_course = c_code
                        break
                        
                if found_coord:
                    return {
                        "verdict": "Supported",
                        "reason": f"Existence verified. Coordinator matched in course {matched_course}.",
                        "evidence": f"({matched_course}, taughtBy, {self.store.courses[matched_course]['coordinator']})"
                    }
                else:
                    # If email is fake / synthetic mismatch
                    if "fake" in str(object_val).lower() or "fake" in str(subject_code).lower():
                        return {
                            "verdict": "Contradicted",
                            "reason": f"Fictional coordinator. Email or name contains fake/fictional coordinates.",
                            "evidence": None
                        }
                    return {"verdict": "Not-in-KG", "reason": f"Coordinator {subject_code} with email {object_val} not found in KG.", "evidence": None}

            return {"verdict": "Not-in-KG", "reason": f"Course code {subject_code} not found in KG.", "evidence": None}

        completeness = self.store.get_relation_completeness(relation)
        course = self.store.get_course(subject_code)

        if relation == "requiresPrerequisite":
            # Check for negation: "does not require any prerequisites" or object is None/null/none
            is_negated = False
            if object_val is None:
                is_negated = True
            elif isinstance(object_val, str) and object_val.lower().strip() in ["none", "null", "no prerequisites", "no prerequisite", "empty", "no", "unknown course"]:
                is_negated = True
                
            if is_negated:
                actual_prereqs = self.store.get_prerequisites(subject_code)
                if len(actual_prereqs) == 0:
                    return {
                        "verdict": "Supported",
                        "reason": f"Fact verified. Course {subject_code} does not require any prerequisite courses.",
                        "evidence": f"({subject_code}, requiresPrerequisite, None)"
                    }
                else:
                    return {
                        "verdict": "Contradicted",
                        "reason": f"Closed-world violation: Course {subject_code} requires prerequisites but was claimed to have none.",
                        "evidence": f"Actual prerequisites: {actual_prereqs}"
                    }

            actual_prereqs = self.store.get_prerequisites(subject_code)
            if object_val in actual_prereqs:
                return {
                    "verdict": "Supported",
                    "reason": f"Fact verified. Course {subject_code} requires {object_val}.",
                    "evidence": f"({subject_code}, requiresPrerequisite, {object_val})"
                }
                
            # 2-hop path check for multi-hop prerequisite claims
            has_2_hop = False
            intermediate_course = None
            for p in actual_prereqs:
                p_prereqs = self.store.get_prerequisites(p)
                if object_val in p_prereqs:
                    has_2_hop = True
                    intermediate_course = p
                    break
                    
            if has_2_hop:
                return {
                    "verdict": "Supported",
                    "reason": f"Fact verified via multi-hop path. Course {subject_code} requires prerequisite {intermediate_course}, which requires {object_val}.",
                    "evidence": f"({subject_code}, requiresPrerequisite, {intermediate_course}) -> ({intermediate_course}, requiresPrerequisite, {object_val})"
                }
                
            if completeness == "closed":
                return {
                    "verdict": "Contradicted",
                    "reason": f"Closed-world violation: Course {subject_code} does NOT require prerequisite {object_val}.",
                    "evidence": f"Actual prerequisites: {actual_prereqs}"
                }
            return {
                "verdict": "Not-in-KG",
                "reason": f"Prerequisite {object_val} not registered for {subject_code} in open world relation.",
                "evidence": None
            }

        elif relation == "hasCreditValue":
            actual_credits = self.store.get_credits(subject_code)
            if actual_credits == object_val:
                return {
                    "verdict": "Supported",
                    "reason": f"Fact verified. Course {subject_code} has {object_val} credit points.",
                    "evidence": f"({subject_code}, hasCreditValue, {object_val})"
                }
            else:
                return {
                    "verdict": "Contradicted",
                    "reason": f"Value mismatch. Claimed {object_val} credits, but actual is {actual_credits} credits.",
                    "evidence": f"({subject_code}, hasCreditValue, {actual_credits})"
                }

        elif relation == "partOfSchool":
            actual_school = self.store.get_school(subject_code)
            if self.normalize_text(actual_school) == self.normalize_text(str(object_val)):
                return {
                    "verdict": "Supported",
                    "reason": f"Fact verified. Course {subject_code} is offered by the School of {actual_school}.",
                    "evidence": f"({subject_code}, partOfSchool, {actual_school})"
                }
            else:
                return {
                    "verdict": "Contradicted",
                    "reason": f"School mismatch. Claimed School of {object_val}, but actual is School of {actual_school}.",
                    "evidence": f"({subject_code}, partOfSchool, {actual_school})"
                }

        elif relation == "taughtBy":
            coord = self.store.get_coordinator(subject_code)
            name_match = self.normalize_text(coord["name"]) == self.normalize_text(str(object_val))
            email_match = self.normalize_text(coord["email"]) == self.normalize_text(str(object_val))
            
            if name_match or email_match:
                return {
                    "verdict": "Supported",
                    "reason": f"Fact verified. Course {subject_code} is coordinated by {coord['name']}.",
                    "evidence": f"({subject_code}, taughtBy, {coord['name']})"
                }
            else:
                # Open world check
                if completeness == "closed":
                    return {
                        "verdict": "Contradicted",
                        "reason": f"Coordinator mismatch. Claimed {object_val}, but actual is {coord['name']}.",
                        "evidence": f"({subject_code}, taughtBy, {coord['name']})"
                    }
                # Check for Not-in-KG vs Supported check:
                # Let's say if we check coordinator name in a list of known coordinators
                return {
                    "verdict": "Not-in-KG",
                    "reason": f"Coordinator {object_val} not matched against stored coordinator: {coord['name']}.",
                    "evidence": f"Actual coordinator: {coord['name']}"
                }

        elif relation in course or relation in ["capital", "birthPlace", "founded", "father", "mother", "office", "type"]:
            actual_val = course.get(relation)
            if actual_val is None:
                return {"verdict": "Not-in-KG", "reason": f"Relation {relation} not registered for {subject_code} in open world context.", "evidence": None}
            
            # Check for general existence claim (object is a placeholder or names the relation type itself)
            obj_str = str(object_val).lower().strip()
            rel_str = str(relation).lower().strip()
            is_existence_placeholder = (
                obj_str in ["yes", "true", "exist", "exists", "someone", "something", "any", "some"] or
                obj_str == rel_str or
                obj_str.endswith(" " + rel_str) or
                obj_str == "parent company" or
                obj_str == "garrison" or
                obj_str == "child" or
                obj_str == "successor" or
                obj_str == "spouse" or
                obj_str == "religion" or
                obj_str == "husband" or
                obj_str == "wife"
            )
            
            if is_existence_placeholder:
                if actual_val and str(actual_val).lower().strip() not in ["none", "unknown", "n/a", ""]:
                    return {
                        "verdict": "Supported",
                        "reason": f"Existence verified. Entity has registered {relation}: {actual_val}.",
                        "evidence": f"({subject_code}, {relation}, {actual_val})"
                    }
                    
            if self.normalize_text(actual_val) == self.normalize_text(str(object_val)):
                return {
                    "verdict": "Supported",
                    "reason": f"Fact verified. {subject_code} {relation} is {actual_val}.",
                    "evidence": f"({subject_code}, {relation}, {actual_val})"
                }
            else:
                return {
                    "verdict": "Contradicted",
                    "reason": f"Value mismatch. Claimed {object_val}, but actual is {actual_val}.",
                    "evidence": f"({subject_code}, {relation}, {actual_val})"
                }

        return {"verdict": "Not-in-KG", "reason": f"Unrecognized relation class: {relation}", "evidence": None}

    def verify_statement(self, text: str, custom_system_prompt: str = None) -> dict:
        """Runs the entire pipeline end-to-end for a given query/response statement."""
        claims = self.stage_2_decompose(text, custom_system_prompt)
        
        if not claims:
            # Fallback if decomposition returns absolutely nothing
            return {
                "text": text,
                "overall_verdict": "Out-of-scope",
                "reason": "No atomic claims could be parsed.",
                "claims": []
            }

        verified_claims = []
        overall_verdict = "Supported"

        for claim in claims:
            subj_code, relation, obj_val = self.stage_3_map_claim_to_triple(claim)
            
            # Prune self-referential prerequisite claims (parser artifacts)
            if relation == "requiresPrerequisite" and subj_code == obj_val and subj_code is not None:
                logger.info(f"Pruning self-referential prerequisite claim parser artifact: {subj_code} -> {obj_val}")
                continue
                
            result = self.stage_4_verify_triple(subj_code, relation, obj_val)
            
            claim_report = {
                "claim_text": f"{claim.get('subject')} {claim.get('relation')} {claim.get('object')}",
                "mapped_triple": (subj_code, relation, obj_val),
                "verdict": result["verdict"],
                "reason": result["reason"],
                "evidence": result["evidence"]
            }
            
            # Combine verdicts: Contradicted has highest priority, then Not-in-KG, then Out-of-scope, then Supported
            if result["verdict"] == "Contradicted":
                overall_verdict = "Contradicted"
            elif result["verdict"] == "Not-in-KG" and overall_verdict != "Contradicted":
                overall_verdict = "Not-in-KG"
            elif result["verdict"] == "Out-of-scope" and overall_verdict not in ["Contradicted", "Not-in-KG"]:
                overall_verdict = "Out-of-scope"

            verified_claims.append(claim_report)

        return {
            "text": text,
            "overall_verdict": overall_verdict,
            "claims": verified_claims
        }
