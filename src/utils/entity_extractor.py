import re
import spacy
from spacy.pipeline import EntityRuler
from typing import List, Dict, Tuple, Any
from loguru import logger

# Load spaCy English model (medium model for better accuracy)
try:
    nlp = spacy.load("en_core_web_md")
    logger.info("Loaded spaCy medium model (en_core_web_md)")
except OSError:
    logger.warning("spaCy medium model (en_core_web_md) not found. Falling back to en_core_web_sm.")
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        nlp = spacy.load("en")

# ─── Custom EntityRuler — catches patterns spaCy sm misses ────────────────────
# Add BEFORE ner so the ruler's labels take priority
if "entity_ruler" not in nlp.pipe_names:
    ruler = nlp.add_pipe("entity_ruler", before="ner")
    _dept_names = [
        "Engineering", "Security", "Research", "Finance", "Human Resources",
        "Legal", "Product", "Customer Success", "Infrastructure", "Data Science",
    ]
    _custom_features = [
        "AI Assistant", "Authentication", "Analytics", "GraphRAG",
        "Project Atlas", "Project Orion", "Project Nebula",
        "Project WeKraft", "WeKraft", "AWS infrastructure",
        "Atlas", "Orion", "Nebula", "OpenAI Agent Workspace",
        "Knowledge Graph", "Hybrid RAG", "Graph Only RAG",
    ]
    _skills = [
        "Python", "TypeScript", "JavaScript", "React", "Next.js",
        "Streamlit", "LangGraph", "LangChain", "OpenAI API",
        "Neo4j", "Cypher", "Pinecone", "BM25", "LlamaParse",
        "spaCy", "GraphRAG", "RAG", "Prompt Engineering",
        "Product Management", "UX Research", "Security Review",
        "API Design", "Data Modeling", "Workflow Automation",
    ]
    _roles = [
        "Product Manager", "Engineering Lead", "Backend Engineer",
        "Frontend Engineer", "Data Scientist", "Security Engineer",
        "Designer", "QA Engineer", "Researcher", "Analyst",
    ]
    
    dept_patterns = [
        {"label": "ORG", "pattern": [{"LOWER": name.lower()}, {"LOWER": "department"}]}
        for name in _dept_names
    ] + [
        # Also catch bare department names used as org references
        {"label": "ORG", "pattern": [{"LOWER": name.lower()}]}
        for name in _dept_names
    ]
    
    feature_patterns = [
        {"label": "PRODUCT", "pattern": [{"LOWER": word.lower()} for word in name.split()]}
        for name in _custom_features
    ]
    
    skill_patterns = [{"label": "SKILL", "pattern": name} for name in _skills]
    role_patterns = [{"label": "ROLE", "pattern": name} for name in _roles]

    ruler.add_patterns(dept_patterns + feature_patterns + skill_patterns + role_patterns)

# Define target entity types we care about for knowledge graph construction
TARGET_ENTITIES = {
    "ORG",         # Companies, agencies, institutions, departments
    "PERSON",      # People, including fictional
    "GPE",         # Countries, cities, states
    "NORP",        # Nationalities, religious or political groups
    "PRODUCT",     # Objects, vehicles, foods, etc. (often tech stacks/software)
    "LOC",         # Non-GPE locations, mountain ranges, bodies of water
    "FAC",         # Buildings, airports, highways, bridges
    "LAW",         # Named laws, policies
    "WORK_OF_ART", # Books, song titles, etc.
    "SKILL",       # User/person skills, tools, frameworks, techniques
    "EXPERIENCE",  # Prior experience domains or historical work areas
    "ROLE",        # Job titles and project roles
    "PROJECT",     # Internal projects and initiatives
    "FEATURE",     # Product features and capabilities
    "TASK",        # Work items, tasks, milestones
}

PERSON_RE = r"[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3}"
ORG_OR_PRODUCT_HINTS = {
    "api", "assistant", "atlas", "automation", "bm25", "dashboard", "graphrag",
    "knowledge graph", "langgraph", "llamaparse", "neo4j", "openai", "pinecone",
    "platform", "project", "rag", "streamlit", "wekraft", "workflow",
}
SKILL_HINTS = {
    "api design", "bm25", "cypher", "data modeling", "graphrag", "javascript",
    "langchain", "langgraph", "llamaparse", "neo4j", "next.js", "pinecone",
    "prompt engineering", "python", "rag", "react", "security review", "spacy",
    "streamlit", "typescript", "ux research", "workflow automation",
}
ROLE_HINTS = {
    "analyst", "architect", "designer", "engineer", "lead", "manager",
    "owner", "researcher", "scientist",
}

def _clean_and_validate_node(name: str) -> str:
    """
    Clean and validate entity or relation node names.
    - Strips leading/trailing '#' characters and whitespace/newlines.
    - Normalizes internal whitespaces/newlines.
    - Strips leading "the " (case-insensitive).
    - Skips if the node starts with '#' or digits followed by whitespace (e.g. '# Rohan', '15\n\n Rohan').
    - Skips if the node is longer than 60 characters or empty/single-char.
    - Skips if the node is a merged phrase or contains verbs/conjunctions that indicate it's a clause.
    """
    if not name:
        return ""
    
    # Normalize whitespaces to check prefix conditions
    norm_temp = re.sub(r"\s+", " ", name).strip()
    if re.match(r"^#\s", norm_temp) or re.match(r"^\d+\s", norm_temp):
        return ""
        
    # Strip leading/trailing '#' and whitespace/newlines/punctuation/quotes
    cleaned = name.strip("# \t\n\r,.-'\"")
    # Normalize internal whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    
    # Strip leading "the " (case-insensitive)
    if cleaned.lower().startswith("the "):
        cleaned = cleaned[4:].strip()
        
    # Clean again after stripping "the"
    cleaned = cleaned.strip("# \t\n\r,.-'\"")
    
    if len(cleaned) > 60 or len(cleaned) <= 1:
        return ""
        
    # Skip if contains verbs/conjunctions indicating it's a merged sentence chunk
    # e.g., "Aarav Mehta Works", "Project Atlas with", "reports quarterly", etc.
    lower_cleaned = cleaned.lower()
    
    # If it ends with or starts with a verb/conjunction/preposition
    words = lower_cleaned.split()
    if not words:
        return ""
    bad_words = {"with", "to", "from", "for", "and", "in", "on", "of", "about", "works", "contributes", "reports", "attends", "collaborates", "depends"}
    if words[0] in bad_words or words[-1] in bad_words:
        return ""
        
    # If the entity contains a verb like "works", "contributes", "collaborates", "reports" as a separate word, it's a merged sentence
    if re.search(r"\b(works|contributes|collaborates|reports|attends|depends)\b", lower_cleaned):
        return ""
        
    return cleaned


def _infer_entity_label(name: str, default: str = "Entity") -> str:
    """Infer labels for entities that come from profile/work-history rules."""
    lower = name.lower().strip()
    if lower in SKILL_HINTS:
        return "SKILL"
    if any(word in lower.split() for word in ROLE_HINTS):
        return "ROLE"
    if lower.startswith("project ") or " project " in lower:
        return "PROJECT"
    if any(hint in lower for hint in ORG_OR_PRODUCT_HINTS):
        return "PRODUCT"
    return default


def _remember_entity(entities: Dict[str, tuple], raw_name: str, label: str) -> None:
    """Store an entity with longer-match deduplication."""
    name = _clean_and_validate_node(raw_name)
    if not name or re.fullmatch(r"[\d\W]+", name):
        return

    if label == "PERSON":
        name = name.title()

    lower = name.lower()
    dominated = False
    to_delete = []
    for stored_lower, (stored_name, _stored_label) in entities.items():
        if lower == stored_lower:
            if len(name) > len(stored_name):
                to_delete.append(stored_lower)
            else:
                dominated = True
            break
        if lower in stored_lower:
            dominated = True
            break
        if stored_lower in lower:
            to_delete.append(stored_lower)

    for key in to_delete:
        del entities[key]

    if not dominated:
        entities[lower] = (name, label)


def _split_profile_items(items: str) -> List[str]:
    """Split comma/and separated skills or past-work phrases into clean nodes."""
    cleaned = re.sub(r"\([^)]*\)", "", items)
    cleaned = re.sub(r"\b(?:and|plus)\b", ",", cleaned, flags=re.IGNORECASE)
    parts = [part.strip(" .;:") for part in cleaned.split(",")]
    return [part for part in parts if _clean_and_validate_node(part)]


def _extract_profile_entities(text: str) -> List[Dict[str, str]]:
    """Extract skills, roles, projects, and experience phrases from profile-like text."""
    entities: Dict[str, str] = {}

    for match in re.finditer(rf"\b({PERSON_RE})\b", text):
        name = _clean_and_validate_node(match.group(1))
        if name and _infer_entity_label(name) == "Entity":
            entities[name] = "PERSON"

    labelled_lists = [
        (r"\bskills?\s*[:=-]\s*(?P<items>[^.\n]+)", "SKILL"),
        (r"\b(?:past|previous|earlier)\s+experience\s*[:=-]\s*(?P<items>[^.\n]+)", "EXPERIENCE"),
        (r"\b(?:role|title)\s*[:=-]\s*(?P<items>[^.\n]+)", "ROLE"),
        (r"\b(?:projects?|products?)\s*[:=-]\s*(?P<items>[^.\n]+)", "PROJECT"),
    ]
    for pattern, label in labelled_lists:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            for item in _split_profile_items(match.group("items")):
                name = _clean_and_validate_node(item)
                if name:
                    entities[name] = label

    return [{"name": name, "label": label} for name, label in entities.items()]


def extract_entities(text: str) -> List[Dict[str, str]]:
    """
    Extract unique entities using improved spaCy NER + custom EntityRuler.

    Improvements over the basic version:
    - EntityRuler pre-labels "X Department" compound patterns as ORG before NER runs.
    - NORP label added (groups, nationalities, team names).
    - Longer-match deduplication: if a shorter entity name is a substring of a
      longer one already seen, prefer the longer one.
    - Whitespace/newline normalisation.
    - Expands entities to full noun chunks if they represent proper names (e.g. "Aarav" -> "Aarav Mehta").
    - Title-cases PERSON names that are not properly capitalized.
    """
    clean_text = re.sub(r"\s+", " ", text).strip()

    # If the input is all-lowercase (typical for user queries), also try
    # a title-cased version so spaCy can recognise proper nouns.
    texts_to_try = [clean_text]
    if clean_text == clean_text.lower() and len(clean_text) < 500:
        texts_to_try.append(clean_text.title())

    # Build a dict: normalised_name -> (original_name, label)
    # For deduplication we prefer the LONGER variant
    entities: Dict[str, tuple] = {}  # key=lower_name, val=(name, label)

    for current_text in texts_to_try:
        doc = nlp(current_text)

        for ent in doc.ents:
            raw_name = ent.text.strip()
            label = ent.label_

            if label not in TARGET_ENTITIES or len(raw_name) < 2:
                continue

            # Expands entity to full proper noun chunk if applicable
            token = ent.root
            expanded_name = raw_name
            if doc.noun_chunks:
                for chunk in doc.noun_chunks:
                    if token in chunk:
                        # Skip leading determiners
                        words = [t.text for t in chunk if t.pos_ != "DET"]
                        chunk_text = " ".join(words).strip()

                        # Normalize person names, but preserve product/brand casing
                        # such as "WeKraft" rather than changing it to "Wekraft".
                        if label == "PERSON":
                            chunk_text = chunk_text.title()

                        # Check if all words in the proper noun chunk start with upper case
                        chunk_words = chunk_text.split()
                        if len(chunk_words) <= 4 and all(w[0].isupper() for w in chunk_words if w and w[0].isalpha()):
                            expanded_name = chunk_text
                        break

            # Clean and validate the extracted entity name
            name = _clean_and_validate_node(expanded_name)
            if not name:
                # Fall back to cleaning raw name if the expanded chunk was rejected
                name = _clean_and_validate_node(raw_name)
                if not name:
                    continue

            # Title case PERSON names
            if label == "PERSON":
                name = name.title()

            lower = name.lower()

            # Skip tokens that are purely numeric or single characters
            if re.fullmatch(r"[\d\W]+", name):
                continue

            # Prefer longer names: if a shorter version is already stored, replace it.
            # Also skip if this name is already a substring of a stored longer name.
            dominated = False
            to_delete = []
            for stored_lower, (stored_name, stored_label) in entities.items():
                if lower == stored_lower:
                    # Exact duplicate — keep whichever is longer
                    if len(name) > len(stored_name):
                        to_delete.append(stored_lower)
                    else:
                        dominated = True
                    break
                if lower in stored_lower:
                    # New name is substring of an existing longer name — skip it
                    dominated = True
                    break
                if stored_lower in lower:
                    # Existing entry is substring of new name — replace it
                    to_delete.append(stored_lower)

            for k in to_delete:
                del entities[k]

            if not dominated:
                entities[lower] = (name, label)

    for ent in _extract_profile_entities(clean_text):
        _remember_entity(entities, ent["name"], ent["label"])

    return [{"name": name, "label": label} for name, label in entities.values()]


def extract_svo_triplets(text: str) -> List[Tuple[str, str, str]]:
    """
    Extract (Subject, Verb/Relation, Object) triplets using spaCy dependency parser.
    """
    doc = nlp(text)
    triplets = []
    
    for sent in doc.sents:
        # Process each sentence
        for token in sent:
            # Look for verbs that act as the main relationship
            if token.pos_ == "VERB":
                subj = None
                obj = None
                
                # Find subject and object linked to this verb
                for child in token.children:
                    # Subject relations
                    if child.dep_ in ("nsubj", "nsubjpass"):
                        subj = _get_noun_chunk(child)
                    # Object relations
                    elif child.dep_ in ("dobj", "attr", "oprd"):
                        obj = _get_noun_chunk(child)
                    # Prepositional objects
                    elif child.dep_ == "prep":
                        for prep_child in child.children:
                            if prep_child.dep_ in ("pobj", "pcomp"):
                                obj = _get_noun_chunk(prep_child)
                                
                # If we found both subject and object, create a triplet
                if subj and obj:
                    relation = token.lemma_.lower()  # Normalize verb to its base form
                    # If verb is 'be', include the preposition/adjective if possible
                    if relation == "be":
                        # Look for attributes or prepositions
                        prep_parts = [child.text for child in token.children if child.dep_ in ("prep", "attr")]
                        if prep_parts:
                            relation = f"is {' '.join(prep_parts)}".lower()
                    
                    triplets.append((subj, relation, obj))
                    
    return triplets

def _get_noun_chunk(token) -> str:
    """
    Helper to reconstruct the full noun phrase/chunk for a given subject/object token.
    """
    # Try to grab the full noun chunk if the token is part of one
    if token.doc.noun_chunks:
        for chunk in token.doc.noun_chunks:
            if token in chunk:
                # Filter out leading determiners (the, a, an)
                words = [t.text for t in chunk if t.pos_ != "DET"]
                return " ".join(words).strip()
    
    # Fallback to token subtree for compound nouns
    words = []
    for t in token.subtree:
        # Only take modifiers, compound words, or the noun itself to keep it clean
        if t.dep_ in ("compound", "amod", "flat") or t == token:
            words.append(t.text)
    return " ".join(words).strip()


def _normalise_relation_type(relation: str) -> str:
    return re.sub(r"[^A-Z0-9_]+", "_", relation.upper()).strip("_") or "RELATED_TO"


def _add_relation(
    relations: List[Dict[str, str]],
    seen: set,
    source: str,
    relation_type: str,
    target: str,
) -> None:
    clean_source = _clean_and_validate_node(source)
    clean_target = _clean_and_validate_node(target)
    if not clean_source or not clean_target or clean_source == clean_target:
        return

    relation = {
        "source": clean_source,
        "type": _normalise_relation_type(relation_type),
        "target": clean_target,
    }
    relation_key = (
        relation["source"].casefold(),
        relation["type"],
        relation["target"].casefold(),
    )
    if relation_key not in seen:
        seen.add(relation_key)
        relations.append(relation)


def _extract_profile_relations(text: str) -> List[Dict[str, str]]:
    """
    Extract high-signal work-profile relations that dependency parsing often misses.

    These rules are intentionally narrow and transparent. They target the document
    shapes users usually upload for org/project memory: "Person has skills in X",
    "Person previously worked at Y", "Person built Z", and "Person owns Project A".
    """
    relations: List[Dict[str, str]] = []
    seen: set = set()

    sentences = [s.strip() for s in re.split(r"[\n.;]+", text) if s.strip()]
    work_verbs = {
        "architects": "ARCHITECT",
        "builds": "BUILD",
        "built": "BUILT",
        "creates": "CREATE",
        "created": "CREATE",
        "designs": "DESIGN",
        "develops": "DEVELOP",
        "implements": "IMPLEMENT",
        "leads": "LEAD",
        "maintains": "MAINTAIN",
        "manages": "MANAGE",
        "owns": "OWN",
        "tests": "TEST",
    }

    for sentence in sentences:
        skill_match = re.search(
            rf"\b(?P<person>{PERSON_RE})\b\s+(?:has|uses|brings|knows|specializes\s+in|is\s+skilled\s+in)\s+"
            rf"(?:(?:skills?|expertise|experience)\s+(?:in|with)\s+)?(?P<items>.+)$",
            sentence,
            flags=re.IGNORECASE,
        )
        if skill_match:
            for item in _split_profile_items(skill_match.group("items")):
                _add_relation(relations, seen, skill_match.group("person"), "SKILLED_IN", item)

        exp_match = re.search(
            rf"\b(?P<person>{PERSON_RE})\b\s+(?:previously|earlier|formerly)\s+"
            rf"(?P<verb>worked\s+(?:at|for|with|on)|served\s+at|built|created|developed|led|designed)\s+"
            rf"(?P<items>.+)$",
            sentence,
            flags=re.IGNORECASE,
        )
        if exp_match:
            verb = exp_match.group("verb").lower()
            relation_type = "HAS_EXPERIENCE_IN"
            if "worked at" in verb or "worked for" in verb or "served at" in verb:
                relation_type = "WORKED_AT"
            elif "worked on" in verb:
                relation_type = "WORKED_ON"
            elif verb in {"built", "created", "developed", "led", "designed"}:
                relation_type = f"PREVIOUSLY_{verb.upper()}"
            for item in _split_profile_items(exp_match.group("items")):
                _add_relation(relations, seen, exp_match.group("person"), relation_type, item)

        profile_exp_match = re.search(
            rf"\b(?P<person>{PERSON_RE})\b.+\b(?:past|previous|earlier)\s+experience\s+(?:includes|with|in)\s+"
            rf"(?P<items>.+)$",
            sentence,
            flags=re.IGNORECASE,
        )
        if profile_exp_match:
            for item in _split_profile_items(profile_exp_match.group("items")):
                _add_relation(relations, seen, profile_exp_match.group("person"), "HAS_EXPERIENCE_IN", item)

        for verb, relation_type in work_verbs.items():
            work_match = re.search(
                rf"\b(?P<person>{PERSON_RE})\b\s+{verb}\s+(?P<target>.+)$",
                sentence,
                flags=re.IGNORECASE,
            )
            if work_match:
                _add_relation(relations, seen, work_match.group("person"), relation_type, work_match.group("target"))

    return relations


def extract_knowledge_graph_elements(text: str) -> Dict[str, Any]:
    """
    Combines Entity extraction and Relation/SVO extraction to construct
    knowledge graph nodes and edges.
    """
    entities = extract_entities(text)
    triplets = extract_svo_triplets(text)
    
    # Filter triplets so that subject and object relate to extracted entities if possible,
    # or keep them if they are clean noun phrases.
    cleaned_relations = []
    seen_relations = set()
    entity_names = {ent["name"].lower() for ent in entities}
    
    for subj, rel, obj in triplets:
        # Clean and validate the original subject and object first
        cleaned_subj = _clean_and_validate_node(subj)
        cleaned_obj = _clean_and_validate_node(obj)
        if not cleaned_subj or not cleaned_obj:
            continue
            
        # Check if subject/object matches or contains any named entities
        subj_match = next((ent["name"] for ent in entities if ent["name"].lower() in cleaned_subj.lower()), cleaned_subj)
        obj_match = next((ent["name"] for ent in entities if ent["name"].lower() in cleaned_obj.lower()), cleaned_obj)
        
        # Clean and validate the resolved matches
        subj_match = _clean_and_validate_node(subj_match)
        obj_match = _clean_and_validate_node(obj_match)
        
        if subj_match and obj_match and subj_match != obj_match:
            relation = {
                "source": subj_match,
                "type": rel.upper().replace(" ", "_"),
                "target": obj_match
            }
            relation_key = (
                relation["source"].casefold(),
                relation["type"],
                relation["target"].casefold(),
            )
            if relation_key not in seen_relations:
                seen_relations.add(relation_key)
                cleaned_relations.append(relation)

    for relation in _extract_profile_relations(text):
        _add_relation(
            cleaned_relations,
            seen_relations,
            relation["source"],
            relation["type"],
            relation["target"],
        )

    entity_map = {ent["name"].casefold(): ent for ent in entities}
    for relation in cleaned_relations:
        for side in ("source", "target"):
            name = relation[side]
            key = name.casefold()
            if key not in entity_map:
                label = "PERSON" if re.fullmatch(PERSON_RE, name) else _infer_entity_label(name)
                ent = {"name": name, "label": label}
                entity_map[key] = ent
                entities.append(ent)
            
    return {
        "entities": entities,
        "relations": cleaned_relations
    }

# ─── Quick Test ───────────────────────────────────────────────────────────────
# if __name__ == "__main__":
#     test_text = (
#         "In September 2025, Microsoft partnered with OpenAI to integrate GPT-4.1 into Azure services. "
#         "Satya Nadella emphasized that this collaboration would accelerate enterprise adoption of generative AI. "
#         "Meanwhile, Google announced Gemini 2.0 at its Mountain View headquarters, highlighting multimodal reasoning capabilities. "
#         "The European Union passed the AI Act in December 2025, requiring companies like Meta and Amazon to comply with strict transparency rules. "
#         "At the same time, Neo4j expanded its partnership with Snowflake to enable real-time graph analytics for financial institutions. "
#         "Dr. Priya Sharma, co-founder of Nexus AI Research Institute, explained that adaptive AI twins could transform healthcare by modeling patient histories. "
#         "Salesforce licensed NARI’s technology to enhance its Einstein platform. "
#         "In Tokyo, SoftBank invested $500 million into robotics startups focusing on humanoid assistants. "
#         "Lionel Messi collaborated with FIFA to promote AI-driven match analytics during the 2026 World Cup. "
#         "The leave policy at Nexus AI Research Institute allows researchers 30 days of paid time off annually."
#     )
#     elements = extract_knowledge_graph_elements(test_text)
#     print("Extracted Entities:")
#     for ent in elements["entities"]:
#         print(f"  - {ent['name']} ({ent['label']})")
        
#     print("\nExtracted Relations:")
#     for rel in elements["relations"]:
#         print(f"  - ({rel['source']}) -[{rel['type']}]-> ({rel['target']})")
