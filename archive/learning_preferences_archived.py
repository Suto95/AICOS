"""
ARCHIVED: Learning Preferences Logic
Removed from active codebase on 2026-10-01 as it was not being used.
Preserved here for reference if needed in the future.
"""

def update_preferences(task, prefs):
    """
    ARCHIVED - This function was not being called.
    Previously incremented frequency counts for each learnable field value.
    
    Updates prefs dict in-place with frequency counts from task.
    Task values should be one of "low", "medium", "high", "yes", "no"
    """
    if not prefs:
        prefs = {}
    
    from .config import LEARNABLE_FIELDS
    
    for field in LEARNABLE_FIELDS:
        if field not in task:
            continue
        
        value_str = str(task[field]).lower()
        if value_str not in ("low", "medium", "high", "yes", "no"):
            continue
        
        if field not in prefs:
            prefs[field] = {"low": 0, "medium": 0, "high": 0, "yes": 0, "no": 0}
        
        prefs[field][value_str] = prefs[field].get(value_str, 0) + 1
    
    return prefs


def global_prior_distribution(field, prefs, memory):
    """
    ARCHIVED - Preference learning function not being used.
    Previously generated categorical value distribution from learned preferences.
    
    Returns dict with keys "low"/"medium"/"high" or "yes"/"no" and their scores.
    """
    if not prefs or field not in prefs:
        # Default uniform distribution
        return {"low": 0.33, "medium": 0.33, "high": 0.34, "yes": 0.5, "no": 0.5}
    
    counts = prefs[field]
    total = sum(counts.values())
    
    if total == 0:
        return {"low": 0.33, "medium": 0.33, "high": 0.34, "yes": 0.5, "no": 0.5}
    
    # Return empirical distribution
    return {k: v / total for k, v in counts.items()}


def predict_categorical_signal(field, task_text, sender, prefs, memory, k=5):
    """
    ARCHIVED - Preference learning function not being used.
    Previously predicted missing signal values using learned distribution.
    
    Uses global_prior_distribution, message context, and sender history to predict values.
    Returns (predicted_value, confidence, source)
    """
    from .logic import compute_similarity
    
    # Get prior distribution from learned preferences
    prior = global_prior_distribution(field, prefs, memory)
    
    # Find k most similar previous messages
    similarities = []
    for i, mem in enumerate(memory[-100:]):  # Search last 100 entries
        if field in mem:
            sim = compute_similarity(task_text, mem.get("text", ""))
            similarities.append((sim, mem[field], mem))
    
    if not similarities:
        # No similar patterns, use prior only
        max_val = max(prior, key=prior.get)
        return (max_val, prior[max_val], "prior")
    
    # Weight by similarity
    similarities.sort(reverse=True)
    weighted_counts = {"low": 0.0, "medium": 0.0, "high": 0.0, "yes": 0.0, "no": 0.0}
    
    for sim, val, mem in similarities[:k]:
        if val in weighted_counts:
            weighted_counts[val] += sim
    
    if sum(weighted_counts.values()) > 0:
        max_val = max(weighted_counts, key=weighted_counts.get)
        confidence = weighted_counts[max_val] / sum(weighted_counts.values())
        return (max_val, confidence, "learned_pattern")
    else:
        max_val = max(prior, key=prior.get)
        return (max_val, prior[max_val], "prior")
