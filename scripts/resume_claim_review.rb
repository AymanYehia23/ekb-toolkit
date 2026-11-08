# Publication requires an editor's claim-by-claim assessment. The digest
# checks freshness; it is not a substitute for that assessment.
require "digest"

def canonical_claim_value(value)
  case value
  when Hash
    value.keys.sort_by(&:to_s).each_with_object({}) do |key, ordered|
      ordered[key.to_s] = canonical_claim_value(value[key])
    end
  when Array
    value.map { |child| canonical_claim_value(child) }
  else
    value
  end
end

def claim_digest(value)
  Digest::SHA256.hexdigest(JSON.generate(canonical_claim_value(value)))
end

def claim_review_basis(item, sources, rules, model)
  refs = item["refs"]
  position = item["path"]
  context = position.scan(/\.(experience|projects|engagements)\[(\d+)\]/)
  parent = model
  placement = context.map do |key, index|
    parent = parent.fetch(key).fetch(index.to_i)
    parent.slice("name", "organization", "title", "association", "employment_type", "primary", "secondary")
  end
  claim_digest([rules, model["schema_version"], model["application_id"], model["target"],
                item, placement, refs.map { |ref| sources.dig(ref, "record_revision") }])
end

def checked_claim_clauses(review, item, fingerprint)
  return unless review.is_a?(Hash) && review.keys.sort == %w[basis_sha256 clauses] && review["basis_sha256"] == fingerprint

  clauses = review["clauses"]
  return unless clauses.is_a?(Array) && !clauses.empty?
  return unless clauses.all? do |clause|
    clause.is_a?(Hash) && clause.keys.sort == %w[basis refs wording] &&
      %w[basis wording].all? { |key| clause[key].is_a?(String) && !clause[key].strip.empty? } &&
      clause["refs"].is_a?(Array) && !clause["refs"].empty? &&
      clause["refs"].uniq == clause["refs"] && (clause["refs"] - item["refs"]).empty?
  end
  return unless clauses.map { |clause| clause["wording"] }.join(" ") == item["text"]
  return unless clauses.flat_map { |clause| clause["refs"] }.uniq.sort == item["refs"].sort

  clauses
end

EXCLUSIVITY = /\b(?:independently|single[- ]?handedly|solely|(?:the )?only (?:engineer|developer|author|owner)|(?:sole|solo) (?:engineer|developer|author|owner)|(?:built|developed|implemented) alone|on (?:my|their) own)\b/i
LEADERSHIP = /\b(?:led\s+(?!to\b)|headed|owned end[- ]to[- ]end|managed (?:the |a )?team)\b/i
MANAGEMENT = /\b(?:line[- ]managed|people[- ]managed|managed (?:the |a )?(?:team|engineers|developers))\b/i
PERSONAL_ACTION = /\b(?:built|developed|implemented|designed|owned|single-handedly|solely|independently)\b/i

def participation_boundary_errors(text, clauses, path, errors)
  offset = 0
  separators = clauses[0...-1].map do |clause|
    offset += clause["wording"].length + 1
    offset - 1
  end
  { EXCLUSIVITY => "independent-ownership", LEADERSHIP => "leadership",
    MANAGEMENT => "people-management" }.each do |pattern, name|
    split = false
    text.scan(pattern) do
      match = Regexp.last_match
      split ||= separators.any? { |position| match.begin(0) < position && match.end(0) > position }
    end
    errors << "#{path} must review the complete #{name} claim in one clause" if split
  end
end

def participation_errors(text, resolved, path, errors)
  levels = resolved.map { |_, source| source["involvement"] }.compact
  # Keep the individual predicate, but remove explicit team descriptors of its
  # object. A subsequent personal predicate still receives its own check.
  personal = text.gsub(/\bteam[- ](?:built|developed|implemented|designed)\b/i, "team")
                 .gsub(/\b(?:built|developed|implemented|designed) by (?:the|a|our) team\b/i, "by the team")
  if levels.include?("contributed") &&
     (personal.match?(PERSONAL_ACTION) || personal.match?(LEADERSHIP) ||
      personal.match?(/(?:\A|\band\s+)(?:created|authored)\b/i))
    refs = resolved.select { |_, source| source["involvement"] == "contributed" }.map(&:first)
    errors << "#{path} overstates contributed source #{refs.join(', ')}"
  end
  if personal.match?(LEADERSHIP) && !levels.empty? && levels.any? { |level| level != "led" }
    errors << "#{path} uses leadership wording without exclusively led sources"
  end
  if personal.match?(MANAGEMENT)
    management_supported = resolved.any? do |_, source|
      scope = [source["statement"], *Array(source["profile_values"])].join(" ")
      affirmative_sentences(scope).any? { |sentence| sentence.match?(MANAGEMENT) }
    end
    unless management_supported
      errors << "#{path} uses people-management wording without explicit source support"
    end
  end
  return unless personal.match?(EXCLUSIVITY)

  supported = !levels.include?("contributed") && resolved.any? do |_, source|
    affirmative_sentences(source["ownership_content"]).any? do |sentence|
      sentence.match?(EXCLUSIVITY) || sentence.match?(/\b(?:built|implemented|developed)\b[^.!?]*\bsolo\b/i)
    end
  end
  errors << "#{path} uses independent-ownership wording without explicit source support" unless supported
end

def affirmative_sentences(value)
  value.to_s.split(/(?<=[.!?])\s+/).reject do |sentence|
    sentence.match?(/\b(?:no evidence|not|never|without|unconfirmed|unverified|unknown|cannot confirm|no proof)\b/i)
  end
end

# Narrow hard stops for demonstrated high-risk patterns. Other causal,
# release, participation and qualification questions are assessed by the editor.
OUTCOME_CLAIMS = [
  [/\b(?:increas\w+|reduc\w+|improv\w+|boost\w+|driv\w+|drove|grew)\s+(?:\w+\s+){0,3}?(?:retention|conversion|revenue|profit|churn|engagement|cost savings)\b/i, "business outcome"],
  [/\b(?:lift\w*|rais\w*|increas\w*|boost\w*|improv\w*) (?:\w+ ){0,3}(?:repeat purchas\w*|repeat orders?)\b/i, "repeat-purchase outcome"],
  [/\bkept customers from leaving\b/i, "customer retention"],
  [/\b(?:eliminat\w+|prevent\w+|end(?:ed|ing)|stopp\w+)\s+(?:all\s+)?(?:production\s+)?(?:outages|downtime|incidents)\b/i, "outage prevention"]
].freeze

def outcome_findings(text, resolved)
  OUTCOME_CLAIMS.filter_map do |pattern, name|
    match = text.match(pattern)
    next unless match
    supported = resolved.any? do |_, source|
      affirmative_sentences(source["statement"]).any? do |sentence|
        sentence.downcase.include?(match[0].downcase)
      end
    end

    next if supported

    "Verify the observed #{name} (#{match[0]}) and attribution against the sources"
  end
end

# These explicit predicates have materially different meanings from their
# client-side or test-source counterparts. Other phrasings still need review.
BACKEND_AUTHORSHIP = /
  \b(?:built|developed|implemented|designed|authored|wrote|created)\s+
  (?:(?:a|the|new|production|server[- ]side|backend|REST|Frappe|ERPNext|BFF|API)\s+){0,5}
  (?:backend(?!\s+(?:APIs?|endpoints?)\b)|server[- ]side\s+(?:logic|APIs?)|endpoints?|APIs?)\b
  (?![- ](?:clients?|integration|responses?|consumption))
/ix
EXTERNAL_CRM = /\b(?:Salesforce|HubSpot|Zoho CRM|Dynamics 365|(?:third[- ]party|external|standalone|separate) CRM)\b/i
DEVICE_MATRIX = /\b(?:cross[- ]device testing|(?:tested|validated|verified)\b[^.!?]{0,70}\bacross (?:multiple |different )?(?:devices|OS versions|iOS and Android versions|Android and iOS versions))\b/i
TEST_AUTHORSHIP = /\b(?:wrote|authored|added|created|implemented)\s+(?:(?:automated|unit|widget|integration|regression|end[- ]to[- ]end)\s+){0,3}tests\b/i
REQUIREMENTS_WORK = /\b(?:gather(?:ed|ing)|elicited|analy[sz]ed|refined|defined|led)\s+(?:(?:the|client|business|product|technical|user|and|refined)\s+){0,5}requirements\b|\brequirements (?:gathering|analysis)\b/i
SUBMISSION_TOTAL = /\b(\d+)\s+((?:(?:client[- ]branded|independent|distinct|separate|mobile|original|native|production|different|unique)\s+)*)(?:apps?|applications?|codebases?)\b[^.!?]{0,100}?\b(\d+)\s+[^.!?]{0,45}?\blistings?\b/i

def scope_findings(text, resolved)
  statements = resolved.flat_map { |_, source| [source["statement"], *Array(source["profile_values"])] }
  positive = statements.flat_map { |statement| affirmative_sentences(statement) }
                       .reject { |sentence| sentence.match?(/\bno\s+(?:separate|external|third[- ]party|production|professional)\b/i) }
  findings = {
    BACKEND_AUTHORSHIP => "Backend/API authorship needs a source for the authored server-side work and its environment.",
    EXTERNAL_CRM => "A named or separate CRM integration needs affirmative evidence for that integration.",
    DEVICE_MATRIX => "Cross-device or OS-version testing needs evidence of the devices or OS versions actually tested.",
    REQUIREMENTS_WORK => "Requirements analysis needs a source documenting the candidate's requirements work."
  }.filter_map do |pattern, message|
    match = text.match(pattern)
    next unless match
    supported = positive.any? do |sentence|
      if pattern == EXTERNAL_CRM
        sentence.downcase.include?(match[0].downcase)
      elsif pattern == BACKEND_AUTHORSHIP && text.match?(/\bproduction\b/i)
        sentence.match?(pattern) && sentence.match?(/\bproduction\b/i)
      else
        sentence.match?(pattern)
      end
    end
    message unless supported
  end
  if text.match?(TEST_AUTHORSHIP) && positive.none? { |sentence| sentence.match?(TEST_AUTHORSHIP) }
    findings << "Test authorship needs a source for the tests the candidate wrote."
  end

  if (match = text.match(SUBMISSION_TOTAL))
    scoped = match[2].casecmp?("client-branded ") && match[0].match?(/\bclient-branded (?:apps|applications)\b/i)
    same_count = positive.any? do |sentence|
      source_total = sentence.match(SUBMISSION_TOTAL)
      source_total && source_total[1] == match[1] && source_total[3] == match[3] &&
        source_total[2].casecmp?("client-branded ")
    end
    unless scoped && same_count
      findings << "Separate client-branded apps from store listings and cite a source confirming both counts and their units."
    end
  end
  findings
end
