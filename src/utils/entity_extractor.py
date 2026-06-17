import spacy
from typing import List, Dict, Tuple, Any

# Load spaCy English model (lightweight)
try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # Fallback in case it wasn't downloaded properly, though it should be
    nlp = spacy.load("en")

# Define target entity types we care about for knowledge graph construction
TARGET_ENTITIES = {
    "ORG",      # Companies, agencies, institutions
    "PERSON",   # People, including fictional
    "GPE",      # Countries, cities, states
    "PRODUCT",  # Objects, vehicles, foods, etc. (often tech stacks/software)
    "LOC",      # Non-GPE locations, mountain ranges, bodies of water
    "FAC",      # Buildings, airports, highways, bridges
    "LAW",      # Named laws
    "WORK_OF_ART" # Books, song titles, etc.
}

def extract_entities(text: str) -> List[Dict[str, str]]:
    """
    Extract unique entities from a text block using spaCy NER.
    Returns:
        List of dicts: [{"name": str, "label": str}]
    """
    doc = nlp(text)
    entities = {}
    
    for ent in doc.ents:
        name = ent.text.strip()
        label = ent.label_
        
        # Standardize labels and filter for high-value entity classes
        if label in TARGET_ENTITIES and len(name) > 1:
            # Clean up punctuation and whitespace
            clean_name = name.replace("\n", " ").strip()
            # Deduplicate by name (prefer the longer version or first seen)
            if clean_name not in entities:
                entities[clean_name] = label
                
    return [{"name": name, "label": label} for name, label in entities.items()]


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
    entity_names = {ent["name"].lower() for ent in entities}
    
    for subj, rel, obj in triplets:
        # Check if subject/object matches or contains any named entities
        subj_match = next((ent["name"] for ent in entities if ent["name"].lower() in subj.lower()), subj)
        obj_match = next((ent["name"] for ent in entities if ent["name"].lower() in obj.lower()), obj)
        
        # Clean up strings
        subj_match = subj_match.strip()
        obj_match = obj_match.strip()
        
        if len(subj_match) > 1 and len(obj_match) > 1 and subj_match != obj_match:
            cleaned_relations.append({
                "source": subj_match,
                "type": rel.upper().replace(" ", "_"),
                "target": obj_match
            })
            
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
