# Apply the reviewed fit and check that the rendered selection follows it.
# Lexical retrieval and the legacy scoring rubric do not grade this map.
MATERIAL_ITEM = /\Aresume\.(?:summary\[\d+\]|experience\[\d+\](?:\.engagements\[\d+\])?\.bullets\[\d+\]|projects\[\d+\]\.details\[\d+\]|skills\[\d+\]\.items\[\d+\])\z/
LEVEL_FITS = {
  "broader-professional" => "professional-experience",
  "practical" => "practical-experience",
  "working-knowledge" => "working-knowledge",
  "familiarity" => "familiarity"
}.freeze

def reviewed_coverage(map, sources, visible, policy, profile, model, errors)
  actual = visible.select { |item| item["path"].match?(MATERIAL_ITEM) }
                  .to_h { |item| [item["path"], item["refs"]] }
  unless actual == map["claim_plan"].transform_values { |claim| claim["refs"] }
    errors << "material résumé claim paths and source references differ from the reviewed claim plan"
  end

  map["requirements"].map do |row|
    term = row["term"]
    fit = row["fit"]
    refs = row["refs"]
    support = refs.filter_map { |ref| sources[ref] }
    if support.length != refs.length
      errors << "#{term}: the requirement map cites an unknown or superseded source"
    end
    public_support = support.select { |source| eligible_source?(source, policy) }
    projects = public_support.select { |source| source["origin"] == "project" }
    declarations = public_support.filter_map do |source|
      source["capability"] if source["skill_heading"]
    end
    minimum = row["minimum_proficiency"]
    threshold = minimum && CAPABILITY_POLICY.fetch("meets_minimum").fetch(minimum)
    level = LEVEL_FITS[fit]
    # A project citation has to support the required environment and scope in
    # the reviewed rationale. It cannot elevate an explicitly capped skill.
    conflicts = sources.values.filter_map do |source|
      capability = source["capability"]
      next unless capability && threshold
      names = [capability["name"], *Array(capability["aliases"])]
      names_overlap = names.any? do |name|
        [term, *row["aliases"]].any? { |alias_name| alignment_term_present?(alias_name, name) }
      end
      capability if names_overlap && (!source["skill_heading"] || !threshold.include?(capability["proficiency"]))
    end
    eligible = case fit
    when "directly-demonstrated"
      !projects.empty? && conflicts.empty?
    when "broader-professional", "practical", "working-knowledge", "familiarity"
      within_level = declarations.any? do |capability|
        capability["proficiency"] == level && (threshold.nil? || threshold.include?(level)) &&
          [capability["name"], *Array(capability["aliases"])].any? do |name|
            [term, *row["aliases"]].any? { |alias_name| alignment_term_present?(alias_name, name) }
          end
      end
      responsibility = fit == "broader-professional" && minimum.nil? &&
        public_support.any? { |source| source["record_path"].start_with?("profile.responsibilities[") }
      within_level || responsibility
    when "skill-gap"
      support.any? do |source|
        source["kind"] == "user-stated" &&
          source.dig("capability", "proficiency") == "learning-target" &&
          source.dig("capability", "gap_confirmed") == true &&
          source.dig("capability", "confirmation_required") == false &&
          [source.dig("capability", "name"), *Array(source.dig("capability", "aliases"))].any? do |name|
            [term, *row["aliases"]].any? { |alias_name| alignment_term_present?(alias_name, name) }
          end
      end
    when "formal-eligibility-met", "formal-eligibility-gap"
      eligible_qualification?(row, support, profile, model)
    when "partial", "transferable"
      public_support.any? { |source| source["origin"] != "capability" || source["skill_heading"] }
    else
      true # An unresolved requirement can cite private leads.
    end
    errors << "#{term}: reviewed #{fit} lacks support at the required scope or proficiency" unless eligible
    paths = row["claim_paths"].select { |path| !(Array(actual[path]) & refs).empty? }
    if row["disposition"] == "included" && row["category"] != "qualification" && (paths.empty? || paths.length != row["claim_paths"].length)
      errors << "#{term}: reviewed inclusion has no visible supporting claim"
    end
    row.merge("coverage" => fit, "selection_reason" => row["reason"], "claim_paths" => paths,
              "status" => row["disposition"], "in_prose" => paths.any? { |path| prose_item?(path) },
              "unused_candidates" => [])
  end
end

def eligible_qualification?(row, support, profile, model)
  minimum_years = row["posting_excerpt"].match(/\b(\d+)\s*\+?\s*years?\b/i)
  return false unless row["screening_finding"] && support.all? do |source|
    source["kind"] == "user-stated" &&
      source["record_path"].match?(/\Aprofile\.(?:experience|work_eligibility|eligibility|education|certifications|languages)\[/)
  end
  return true unless minimum_years

  # Only confirmed, cited employment entries count toward a time threshold.
  timeline = Array(profile["experience"]).select { |entry| row["refs"].include?(entry["id"]) }
  return false if timeline.empty?
  years = confirmed_experience_years({"experience" => timeline}, model)
  return false unless years
  (years >= minimum_years[1].to_i) == (row["fit"] == "formal-eligibility-met")
end
