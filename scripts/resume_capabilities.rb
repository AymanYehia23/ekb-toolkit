require "open3"

# Keep capability declarations separate from generic profile text. In
# particular, examples and private limitations never license public prose.
CAPABILITY_POLICY_PATH = File.expand_path("../config/capabilities.json", __dir__)
CAPABILITY_POLICY = JSON.parse(File.read(CAPABILITY_POLICY_PATH, encoding: "UTF-8"))

def collect_capability_sources(profile, sources, errors)
  script = File.join(__dir__, "ekb_capabilities.py")
  output, diagnostic, status = Open3.capture3(
    ENV.fetch("EKB_PYTHON", "python3"), script, stdin_data: JSON.generate(profile)
  )
  unless status.success?
    errors << "candidate capabilities: #{diagnostic.strip}"
    return
  end
  JSON.parse(output).each do |row|
    id = row.fetch("id")
    level = row.fetch("proficiency")
    confirmed = row["kind"] == "user-stated" && row["confirmation_required"] == false
    sources[id] = {
      "origin" => "capability",
      "record_path" => "profile.capabilities",
      "record_revision" => claim_digest(row),
      "kind" => row["kind"],
      "capability" => row,
      "skill_heading" => confirmed ? CAPABILITY_POLICY["skill_headings"][level] : nil,
      "numeric_content" => row["name"]
    }
  end
end

def validate_capability_item(item, resolved, model, errors, all_sources, reviewed)
  capabilities = resolved.select { |_, source| source["origin"] == "capability" }
  path = item["path"]
  if capabilities.empty?
    if item["heading"]
      neutral = %w[skills technologies languages mobile architecture integrations testing delivery]
      neutral += ["engineering practices", "delivery and quality", "ai tools", "device and hardware",
                  "mobile development", "languages and frameworks", "frameworks", "data and storage",
                  "platforms and tools", "backend", "frontend", "collaboration"]
      if item["text"].match?(/\b(?:expert|advanced|mastery|proficien\w*|production-grade|professional skills|working knowledge|familiarity|practical experience)\b/i) ||
         (reviewed && !neutral.include?(item["text"].downcase))
        errors << "#{path} must use a neutral heading or cite declarations for the exact proficiency"
      end
    elsif path.match?(/\Aresume\.skills\[\d+\]\.items\[\d+\]\z/)
      declared = all_sources.values.any? do |source|
        row = source["capability"]
        row && [row["name"], *Array(row["aliases"])].any? do |name|
          alignment_term_present?(item["text"], name)
        end
      end
      errors << "#{path} must use the canonical capability declaration and proficiency heading" if declared
    end
    return
  end
  if item["heading"]
    unless capabilities.length == resolved.length &&
           capabilities.all? { |_, source| source["skill_heading"] == item["text"] }
      errors << "#{path} must use the capability proficiency heading for all cited skills"
    end
    return
  end

  position = path.match(/\Aresume\.skills\[(\d+)\]\.items\[\d+\]\z/)
  source = capabilities.first.last
  unless position && resolved.length == 1 && !item["url"] &&
         source["skill_heading"] && model["skills"][position[1].to_i]["name"] == source["skill_heading"] &&
         item["text"] == source.dig("capability", "name")
    errors << "#{path} must cite one confirmed capability with its exact skill name under its proficiency heading"
  end
end
