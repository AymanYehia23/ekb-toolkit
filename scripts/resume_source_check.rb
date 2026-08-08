#!/usr/bin/env ruby

require "date"
require "json"
require "optparse"
require "set"
require "yaml"

options = {}
OptionParser.new do |parser|
  parser.banner = "usage: resume_source_check.rb --model FILE --profile FILE --projects DIR"
  parser.on("--model FILE") { |value| options[:model] = value }
  parser.on("--profile FILE") { |value| options[:profile] = value }
  parser.on("--projects DIR") { |value| options[:projects] = value }
  parser.on("--ranking FILE") { |value| options[:ranking] = value }
  parser.on("--index FILE") { |value| options[:index] = value }
  parser.on("--shortlist FILE") { |value| options[:shortlist] = value }
  parser.on("--rubric FILE") { |value| options[:rubric] = value }
end.parse!

missing = %i[model profile projects].reject { |key| options[key] }
unless missing.empty?
  warn "missing required options: #{missing.join(', ')}"
  exit 2
end

# Read as UTF-8 explicitly. Without this the scripts inherit whatever
# Encoding.default_external the shell provides, and a resume containing a euro
# sign, an accented name, or any non-ASCII byte crashes the checker before it
# validates anything.
def read_utf8(path)
  File.read(path, encoding: "UTF-8")
end

def load_yaml(path)
  YAML.safe_load(read_utf8(path), permitted_classes: [Date], aliases: false) || {}
rescue Psych::Exception => e
  raise "cannot parse YAML #{path}: #{e.message}"
end

def normalize_involvement(record)
  involvement = record["involvement"]
  return involvement if involvement

  {
    "sole" => "implemented",
    "shared" => "contributed",
    "unclear" => "unknown"
  }[record["attribution"]] || "unknown"
end

def flatten_profile_values(value, values = [])
  case value
  when Hash
    value.each do |key, child|
      next if %w[id kind projects].include?(key)
      flatten_profile_values(child, values)
    end
  when Array
    value.each { |child| flatten_profile_values(child, values) }
  when String, Numeric
    values << value.to_s
  end
  values
end

def normalize_profile_text(value)
  value.to_s.downcase
    .sub(%r{\Ahttps?://}, "")
    .sub(/\Awww\./, "")
    .gsub(/[^a-z0-9]+/, " ")
    .strip
end

def profile_value_variants(values)
  values.flat_map do |value|
    variants = [value]
    if (match = value.match(/\A(\d{4})-(\d{2})\z/))
      year = match[1]
      month = match[2].to_i
      if month.between?(1, 12)
        variants << "#{Date::ABBR_MONTHNAMES[month]} #{year}"
        variants << "#{Date::MONTHNAMES[month]} #{year}"
      end
    end
    variants
  end
end

def profile_supports_text?(text, values)
  variants = profile_value_variants(values).map { |value| normalize_profile_text(value) }.reject(&:empty?)
  normalized = normalize_profile_text(text)
  return true if variants.include?(normalized)

  tokens = normalized.split
  corpus_tokens = variants.join(" ").split.uniq
  !tokens.empty? && tokens.all? { |token| corpus_tokens.include?(token) }
end

def collect_profile_sources(value, sources, errors, path = "profile")
  case value
  when Hash
    if value["id"].is_a?(String) && value["id"].start_with?("profile-")
      id = value["id"]
      if sources.key?(id)
        errors << "duplicate source ID #{id} at #{path}"
      else
        sources[id] = {
          "origin" => "profile",
          "kind" => value["kind"],
          "involvement" => nil,
          "profile_values" => flatten_profile_values(value),
          "numeric_content" => JSON.generate(value.reject { |key, _child| %w[id kind].include?(key) })
        }
      end
    end
    value.each { |key, child| collect_profile_sources(child, sources, errors, "#{path}.#{key}") }
  when Array
    value.each_with_index { |child, index| collect_profile_sources(child, sources, errors, "#{path}[#{index}]") }
  end
end

# --- Hyperlink registry ----------------------------------------------------
#
# Automatic hyperlinking is the default, which makes the opposite risk the real
# one: a plausible-looking address that nobody confirmed. Every url a document
# renders must appear in profile.yaml, and every project or organization link
# must be marked `link_status: confirmed` there. A caveat recorded only in prose
# cannot be enforced, so the status field is what this check reads.

def normalize_url(value)
  value.to_s.strip.downcase.sub(%r{/\z}, "")
end

def collect_link_registry(profile)
  registry = {"allowed" => {}, "blocked" => {}, "projects" => {}, "organizations" => {}}

  register = lambda do |url, owner, status|
    key = normalize_url(url)
    next if key.empty?
    bucket = status == "confirmed" ? "allowed" : "blocked"
    registry[bucket][key] = {"owner" => owner, "status" => status}
  end

  Array(profile["contact"]).each do |entry|
    next unless entry.is_a?(Hash)
    register.call(entry["url"], entry["id"], "confirmed")
  end
  Array(profile["links"]).each do |entry|
    next unless entry.is_a?(Hash)
    register.call(entry["url"], entry["id"], "confirmed")
  end
  Array(profile["certifications"]).each do |entry|
    next unless entry.is_a?(Hash)
    register.call(entry["url"], entry["id"], "confirmed")
  end
  Array(profile["organization_links"]).each do |entry|
    next unless entry.is_a?(Hash)
    status = entry["link_status"] || "confirmed"
    register.call(entry["url"], entry["organization"], status)
    registry["organizations"][entry["organization"].to_s] = {"url" => entry["url"], "status" => status}
  end
  Array(profile["project_links"]).each do |entry|
    next unless entry.is_a?(Hash)
    status = entry["link_status"] || "confirmed"
    slots = %w[play_store app_store repo docs portfolio].filter_map do |slot|
      entry[slot] && [slot, entry[slot]]
    end
    slots.each { |(_slot, url)| register.call(url, entry["project"], status) }
    registry["projects"][entry["project"].to_s] = {"slots" => slots.to_h, "status" => status}
  end
  Array(profile["education"]).each do |entry|
    next unless entry.is_a?(Hash)
    register.call(entry["url"], entry["id"], "confirmed")
    graduation = entry["graduation_project"]
    next unless graduation.is_a?(Hash)
    %w[repo url docs].each { |slot| register.call(graduation[slot], graduation["id"], "confirmed") }
  end
  registry
end

def check_model_links(value, registry, errors, path = "resume")
  case value
  when Hash
    if value.key?("url") && value.key?("text")
      key = normalize_url(value["url"])
      blocked = registry["blocked"][key]
      if blocked
        errors << "#{path}.url is recorded with link_status #{blocked['status'].inspect} for " \
                  "#{blocked['owner']} and may not be rendered"
      elsif !registry["allowed"].key?(key)
        errors << "#{path}.url is not a link recorded in profile.yaml"
      end
      return
    end
    value.each { |key, child| check_model_links(child, registry, errors, "#{path}.#{key}") }
  when Array
    value.each_with_index { |child, index| check_model_links(child, registry, errors, "#{path}[#{index}]") }
  end
end

def organization_link_warnings(model, registry)
  warnings = []
  Array(model["experience"]).each do |entry|
    next unless entry.is_a?(Hash)
    organization = entry["organization"]
    next unless organization.is_a?(Hash)
    recorded = registry["organizations"][organization["text"].to_s]
    next if recorded.nil?
    next unless recorded["status"] == "confirmed"
    if organization["url"].to_s.strip.empty?
      warnings << "employer #{organization['text']} has a confirmed website in profile.yaml but renders unlinked"
    end
  end
  warnings
end

# --- Project ranking -------------------------------------------------------
#
# Selection should prefer the strongest available evidence, so an inversion —
# a lower-ranked project selected while a higher-ranked one is left out — is
# worth surfacing. It is a warning, never an error: the target role, a counting
# rule, or a placement constraint legitimately overrides rank, and only the
# agent's delivery note can say which applied.

def rank_warnings(ranking, selected_projects, eligible_projects, resume_mode, relevant_projects = nil)
  return [] if ranking.nil?
  entries = Array(ranking["projects"]).select { |entry| entry.is_a?(Hash) }
  return [] if entries.empty?

  ranks = entries.to_h { |entry| [entry["project"].to_s, entry["rank"]] }
  eligible = entries.select do |entry|
    eligible_projects.include?(entry["project"].to_s) && entry["placement"] != "education"
  end
  selected = selected_projects.to_a.select { |project| ranks.key?(project) }

  warnings = []
  if resume_mode == "master"
    highest = eligible.min_by { |entry| entry["rank"] }
    if highest && !selected_projects.include?(highest["project"].to_s)
      warnings << "master resume omits highest-ranked eligible project " \
                  "#{highest['project']} (rank #{highest['rank']}) — select it somewhere or record the binding cap, " \
                  "counting rule, or stronger non-redundant coverage reason"
    end
  end
  return warnings if selected.empty?

  unranked = selected_projects.to_a.reject { |project| ranks.key?(project) }
  unless unranked.empty?
    warnings << "selected projects are absent from the ranking: #{unranked.sort.join(', ')}"
  end
  lowest = selected.map { |project| ranks[project] }.max
  # A targeted resume SHOULD skip higher-ranked projects that do not serve the
  # target, so an unfiltered inversion warning fires on essentially every run
  # and trains the reader to skim the whole warning block. Only report a skipped
  # project that could actually have covered one of this target's requirements.
  skipped = eligible
    .reject { |entry| selected_projects.include?(entry["project"].to_s) }
    .select { |entry| entry["rank"] < lowest }
    .select { |entry| relevant_projects.nil? || relevant_projects.include?(entry["project"].to_s) }
    .map { |entry| "#{entry['project']} (rank #{entry['rank']})" }
  unless skipped.empty?
    warnings << "rank inversion: selected a project ranked #{lowest} while skipping " \
                "target-relevant #{skipped.join(', ')} — state the reason in the delivery summary"
  end
  warnings
end

# --- Evidence shortlist ----------------------------------------------------
#
# applications/<id>.evidence.yaml records which candidate answered each
# requirement and why. It is the one artifact that makes selection reviewable,
# so the checks here are about the decision being MADE and HONORED, never about
# which decision was right. That judgement needs the job description.

def shortlist_findings(shortlist, prose_refs, visible_refs, errors, warnings)
  return unless shortlist.is_a?(Hash)
  entries = Array(shortlist["requirements"]).select { |entry| entry.is_a?(Hash) }
  return if entries.empty?

  undecided = []
  entries.each do |entry|
    term = entry["term"].to_s
    required = entry["priority"].to_s == "required"
    selected = Array(entry["selected"]).map(&:to_s)
    reason = entry["reason"].to_s.strip
    candidates = Array(entry["candidates"]).filter_map { |c| c["ref"].to_s if c.is_a?(Hash) }
    profile_candidates = Array(entry["profile_candidates"])
      .filter_map { |c| c["ref"].to_s if c.is_a?(Hash) }

    if required && selected.empty? && reason.empty?
      undecided << term
      next
    end

    # A recorded pick that never reaches the document means the shortlist and
    # the resume disagree about what was decided.
    unused = selected.reject do |ref|
      if candidates.include?(ref)
        prose_refs.include?(ref)
      elsif profile_candidates.include?(ref)
        visible_refs.include?(ref)
      else
        prose_refs.include?(ref) || visible_refs.include?(ref)
      end
    end
    unless unused.empty?
      warnings << "shortlist for \"#{term}\" selects #{unused.join(', ')} but the resume does not " \
                  "cite each project candidate in Summary, Experience, or Selected Projects, or each " \
                  "profile candidate anywhere visible"
    end

    # Skipping the top candidate is often correct, but it is the decision most
    # worth stating, so require the reason to exist.
    next if candidates.empty? || selected.empty?
    top = candidates.first
    if !selected.include?(top) && reason.empty?
      warnings << "shortlist for \"#{term}\" skips its strongest candidate #{top} with no reason"
    end
  end

  unless undecided.empty?
    errors << "evidence shortlist has no decision for required requirements: " \
              "#{undecided.join(', ')}. Record `selected` or `reason` for each"
  end
end

# --- Selection score -------------------------------------------------------
#
# Scores how well the resume used the evidence available to it, against the
# explicit rubric in resume/review-rubric.json. Deliberately NOT a fit score:
# requirements with no eligible evidence are excluded from every denominator, so
# an honest gap such as a seniority bar cannot lower it. Private, and never
# rendered into a document.

def selection_score(rubric, coverage_report, shortlist)
  return nil if rubric.nil?
  dimensions = rubric["dimensions"] || {}
  # Normalize workspace-level rubrics created before this dimension was
  # renamed. The old label encoded the bad incentive, so use only its weight
  # and publish the corrected name and semantics in the report.
  if !dimensions.key?("required_coverage") && dimensions.key?("required_demonstrated")
    dimensions = dimensions.merge("required_coverage" => dimensions["required_demonstrated"])
  end
  decisions = {}
  Array(shortlist && shortlist["requirements"]).each do |entry|
    next unless entry.is_a?(Hash)
    decisions[entry["term"].to_s] = entry
  end

  required = coverage_report.select { |entry| entry["priority"].to_s == "required" }
  # A requirement the knowledge base genuinely cannot answer is not a selection
  # failure. Scoreable means: eligible project evidence exists for it.
  scoreable = required.select do |entry|
    decision = decisions[entry["term"].to_s]
    entry["coverage"] == "demonstrated" ||
      !Array(entry["unused_candidates"]).empty? ||
      (decision && !Array(decision["candidates"]).empty?)
  end
  critical = scoreable.select { |entry| entry["critical"] }

  demonstrated_ratio = lambda do |set|
    return nil if set.empty?
    set.count { |entry| entry["coverage"] == "demonstrated" }.to_f / set.length
  end

  # Critical requirements need project evidence. A non-critical requirement is
  # at its expected depth when it is either demonstrated or supported as stated.
  # This prevents a commodity-tool keyword such as Git from gaining score merely
  # because an internal recovery anecdote was promoted into Experience.
  coverage_ratio = lambda do |set|
    return nil if set.empty?
    set.count do |entry|
      entry["coverage"] == "demonstrated" ||
        (!entry["critical"] && entry["coverage"] == "stated")
    end.to_f / set.length
  end

  strongest = nil
  unless decisions.empty?
    judged = scoreable.filter_map do |entry|
      # Do not reward selecting project evidence for a non-critical requirement
      # that is already correctly stated. If a project record is used anyway,
      # judge its strength because it consumed public resume space.
      next if !entry["critical"] && entry["coverage"] != "demonstrated"
      decision = decisions[entry["term"].to_s]
      next if decision.nil?
      candidates = Array(decision["candidates"]).filter_map { |c| c["ref"].to_s if c.is_a?(Hash) }
      next if candidates.empty?
      selected = Array(decision["selected"]).map(&:to_s)
      next 0.0 if selected.empty?
      # Full credit for the top candidate, decaying with the best rank used.
      best = selected.filter_map { |ref| candidates.index(ref) }.min
      next 0.0 if best.nil?
      1.0 / (1 + best)
    end
    strongest = judged.empty? ? nil : judged.sum / judged.length
  end

  recorded = nil
  unless required.empty? || decisions.empty?
    recorded = required.count do |entry|
      decision = decisions[entry["term"].to_s]
      decision && (!Array(decision["selected"]).empty? || !decision["reason"].to_s.strip.empty?)
    end.to_f / required.length
  end

  values = {
    "required_coverage" => coverage_ratio.call(scoreable),
    "critical_demonstrated" => demonstrated_ratio.call(critical),
    "strongest_evidence_used" => strongest,
    "decisions_recorded" => recorded
  }

  earned = 0.0
  available = 0.0
  breakdown = {}
  values.each do |name, value|
    weight = (dimensions.dig(name, "weight") || 0).to_f
    next if weight.zero?
    if value.nil?
      breakdown[name] = {"value" => nil, "weight" => weight, "note" => "not measurable"}
      next
    end
    available += weight
    earned += weight * value
    breakdown[name] = {"value" => (value * 100).round, "weight" => weight}
  end
  return nil if available.zero?

  {
    "rubric_version" => rubric["version"],
    "score" => ((earned / available) * 100).round,
    "scoreable_required" => scoreable.length,
    "excluded_no_evidence" => required.length - scoreable.length,
    "dimensions" => breakdown
  }
end

# --- External signals ------------------------------------------------------
#
# What the separate resume-review prompt penalizes that the selection score
# deliberately ignores. The selection score measures the TOOLKIT and excludes
# requirements the knowledge base cannot answer; the reviewer's overall figure
# explicitly weighs "skills, experience, soft skills, and seniority alignment",
# so those exclusions are exactly its blind spot.
#
# Reported separately, never blended. None of this licenses inflating anything:
# a seniority gap is stated plainly in delivery, never narrowed.

def profile_experience_months(profile)
  starts = []
  ends = []
  Array(profile["experience"]).each do |entry|
    next unless entry.is_a?(Hash)
    start_month = month_index(entry["start"])
    next unless start_month
    starts << start_month
    finish = entry["end"].to_s == "present" ? month_index(Date.today.strftime("%Y-%m")) : month_index(entry["end"])
    ends << (finish || start_month)
  end
  return nil if starts.empty?
  # Span from first role to last, so concurrent roles are not double counted.
  ends.max - starts.min
end

def required_years_from(coverage_report)
  coverage_report.each do |entry|
    match = entry["term"].to_s.match(/(\d+)\s*\+?\s*years?/i)
    return match[1].to_i if match
  end
  nil
end

def external_signals(model, profile, coverage_report, limit = 15)
  return nil if coverage_report.empty?

  # A supported non-critical skill is not a gap. Report unsupported items and
  # critical capabilities that are only stated, ordered by likely cost.
  gap = coverage_report
    .select do |entry|
      entry["coverage"] == "unsupported" ||
        (entry["critical"] && entry["coverage"] != "demonstrated")
    end
    .sort_by do |entry|
      [
        entry["priority"].to_s == "required" ? 0 : 1,
        entry["critical"] ? 0 : 1,
        entry["coverage"] == "unsupported" ? 0 : 1
      ]
    end
    .first(limit)
    .map do |entry|
      {
        "term" => entry["term"],
        "coverage" => entry["coverage"],
        "priority" => entry["priority"],
        "critical" => entry["critical"],
        "fixable" => !Array(entry["unused_candidates"]).empty?
      }
    end

  seniority = nil
  required_years = required_years_from(coverage_report)
  if required_years
    months = profile_experience_months(profile)
    if months
      held = (months / 12.0).round(1)
      seniority = {
        "required_years" => required_years,
        "confirmed_years" => held,
        "status" => held + 0.25 >= required_years ? "met" : "below",
        "note" => "Confirmed from the profile timeline. Never narrow this gap in the document; state it."
      }
    end
  end

  critical_unsupported = coverage_report.count do |entry|
    entry["critical"] && entry["coverage"] == "unsupported"
  end

  {
    "keyword_gap" => gap,
    "keyword_gap_fixable" => gap.count { |entry| entry["fixable"] },
    "seniority" => seniority,
    "unsupported_critical" => critical_unsupported,
    "market" => model.dig("target", "market"),
    "note" => "Predicts what an external reviewer penalizes. Not part of the selection score."
  }
end

def collect_visible_items(value, items, errors, path = "resume")
  case value
  when Hash
    has_text = value.key?("text")
    has_source = value.key?("source_ref") || value.key?("source_refs")
    if has_text || has_source
      allowed = %w[source_ref source_refs text url]
      unless (value.keys - allowed).empty? && has_text && has_source
        errors << "#{path} must contain text and source_ref or source_refs, and may contain url"
      end
      unless value["text"].is_a?(String) && !value["text"].strip.empty?
        errors << "#{path}.text must be a non-empty string"
      end

      # Composition. One source stays the default; `source_refs` exists for the
      # claims that are inherently plural, such as shipping counts spanning many
      # apps, which no single record can support. Every listed source must be
      # independently eligible and the text must be entailed by their
      # conjunction, so composition widens what is sayable without weakening
      # what must be true.
      if value.key?("source_ref") && value.key?("source_refs")
        errors << "#{path} must use source_ref or source_refs, not both"
      end
      refs =
        if value.key?("source_refs")
          unless value["source_refs"].is_a?(Array) && value["source_refs"].length >= 2
            errors << "#{path}.source_refs must list at least two source IDs; use source_ref for one"
          end
          list = Array(value["source_refs"])
          if list.length > MAX_COMPOSED_SOURCES
            errors << "#{path}.source_refs composes #{list.length} sources; " \
                      "#{MAX_COMPOSED_SOURCES} is the maximum a reader can audit"
          end
          if list.uniq.length != list.length
            errors << "#{path}.source_refs repeats a source"
          end
          list
        else
          [value["source_ref"]]
        end
      refs = refs.select { |ref| ref.is_a?(String) && !ref.strip.empty? }
      if refs.empty?
        errors << "#{path} needs at least one non-empty source ID"
      end
      if value.key?("url")
        # A hyperlink target is presentation, not a factual claim, so it needs no
        # source of its own — but it must be a safe, non-empty absolute target.
        unless value["url"].is_a?(String) && value["url"].strip.match?(%r{\A(https://|mailto:|tel:)})
          errors << "#{path}.url must start with https://, mailto:, or tel:"
        end
      end
      items << {
        "path" => path,
        "text" => value["text"],
        # `source_ref` stays the primary for every single-source consumer;
        # `refs` is the complete list a composed item resolves to.
        "source_ref" => refs.first,
        "refs" => refs,
        "url" => value["url"]
      }
      return
    end
    value.each { |key, child| collect_visible_items(child, items, errors, "#{path}.#{key}") }
  when Array
    value.each_with_index { |child, index| collect_visible_items(child, items, errors, "#{path}[#{index}]") }
  end
end

def check_summary_project_links(visible_items, sources, registry, errors, warnings)
  visible_items.each do |item|
    next unless item["path"].match?(/\Aresume\.summary\[\d+\]\z/)

    # A composed summary item spanning several projects has no single project
    # destination, so the one-URL rule does not apply to it.
    item_projects = Array(item["refs"]).filter_map { |ref| sources.dig(ref, "project") }.uniq
    next unless item_projects.length == 1
    project = item_projects.first
    next if project.to_s.empty?

    recorded = registry["projects"][project]
    confirmed_slots =
      if recorded && recorded["status"] == "confirmed"
        recorded["slots"].values.reject { |url| url.to_s.strip.empty? }
      else
        []
      end

    if confirmed_slots.empty?
      warnings << "summary item backed by #{project} has no confirmed project link in profile.yaml"
      next
    end

    url = item["url"].to_s.strip
    if url.empty?
      errors << "#{item['path']} is backed by project #{project} and must carry one of its confirmed project links"
      next
    end

    allowed = confirmed_slots.map { |candidate| normalize_url(candidate) }
    unless allowed.include?(normalize_url(url))
      errors << "#{item['path']}.url must belong to its source project #{project}"
    end
  end
end

def numeric_tokens(value)
  # Treat a quantifier as one semantic unit. This avoids accepting "4" merely
  # because the source contains "40", while allowing common CV formats.
  value.to_s.scan(/(?<![A-Za-z0-9])(?:[$€£]\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s?[KMBkmb]\+?(?![A-Za-z]))?(?:\s?%|\s+(?:hours?|days?|weeks?|months?|years?|users?|customers?|people|files?|modules?|screens?|projects?|devices?|formats?|team\s+members?))?/)
    .map { |token| token.strip }
    .reject(&:empty?)
end

def canonical_numeric_token(value)
  value.downcase.gsub(/\s+/, " ").delete(",").sub(/\A([$€£])\s+/, '\\1')
end

# Spelled-out quantities bypassed the numeric check entirely, because
# `numeric_tokens` only ever matched digits. A resume said "three clients
# adopted the service" while its cited record said two, and every gate passed.
#
# "one" is deliberately excluded: it is overwhelmingly an article rather than a
# count ("one call", "in one action", "a single owner per failure class"), and
# checking it produces noise without catching claims. Counts that matter to a
# reader start at two.
WORD_NUMBERS = %w[
  two three four five six seven eight nine ten eleven twelve thirteen fourteen
  fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty
  seventy eighty ninety hundred thousand million
].freeze

def word_number_tokens(value)
  value.to_s.downcase.scan(/(?<![[:alnum:]])(#{WORD_NUMBERS.join('|')})(?![[:alnum:]])/).flatten
end

def alignment_term_present?(text, term)
  text.match?(/(?<![[:alnum:]])#{Regexp.escape(term)}(?![[:alnum:]])/i)
end

# --- Coverage strength -----------------------------------------------------
#
# `status: matched` only ever meant "an alias appears somewhere and one eligible
# source is cited". The Skills section satisfies both on its own, so a required
# capability could be reported as matched while the achievement that actually
# demonstrates it went unused. The 2026-07-28 review found exactly that: a
# `required` performance requirement matched to a skills line while the
# portfolio's only before/after measurement sat unselected.
#
# Coverage is DERIVED here rather than authored in the model, so it cannot be
# asserted into existence:
#   demonstrated — a curated project record is cited in Summary, Experience,
#                  or Selected Projects. The resume shows the capability.
#   stated       — cited only by a profile fact, or only in a list section.
#                  The resume claims the capability.
#   unsupported  — no eligible evidence.

# A composed claim past this many sources stops being auditable by a reader who
# wants to check it, which is the property that makes composition safe at all.
MAX_COMPOSED_SOURCES = 4

PROSE_SECTIONS = %w[resume.summary resume.experience resume.projects].freeze

def prose_item?(path)
  PROSE_SECTIONS.any? { |prefix| path.to_s.start_with?(prefix) }
end

def coverage_for(refs, sources, visible_items)
  citing = visible_items.select { |item| !(refs & Array(item["refs"])).empty? }
  return "unsupported" if citing.empty?

  demonstrated = citing.any? do |item|
    prose_item?(item["path"]) &&
      (refs & Array(item["refs"])).any? { |ref| sources.dig(ref, "origin") == "project" }
  end
  demonstrated ? "demonstrated" : "stated"
end

# --- Understatement gate ---------------------------------------------------
#
# Every other check in this file stops the resume from claiming too much. This
# one is the mirror: it fires when eligible evidence that would have
# demonstrated a required capability was left on the shelf. It reads the
# generated evidence index rather than the model's own `evidence_refs`, because
# a requirement can only under-report its candidates if it is the thing being
# audited.

ALIAS_STOPWORDS = %w[the and for with app apps code data new use using team work years year].freeze

def usable_alias?(value)
  text = value.to_s.strip.downcase
  return false if text.length < 3
  return false if text.match?(/\A[\d\s+.]+\z/)
  !ALIAS_STOPWORDS.include?(text)
end

def index_candidates(index, aliases)
  return [] if index.nil?
  terms = aliases.select { |value| usable_alias?(value) }.map { |value| value.to_s.downcase.strip }
  return [] if terms.empty?

  capabilities = index["capabilities"] || {}
  matched_ids = {}
  terms.each do |term|
    Array(capabilities[term]).each { |id| matched_ids[id] = true }
  end
  Array(index["evidence_bridges"]).each do |bridge|
    next unless bridge.is_a?(Hash)
    bridge_text = Array(bridge["aliases"]).join(" ")
    next unless terms.any? { |term| alignment_term_present?(bridge_text, term) }
    Array(bridge["records"]).each { |id| matched_ids[id] = true }
  end

  Array(index["records"]).select do |record|
    next false unless record.is_a?(Hash)
    next false unless record["eligible"]
    next true if matched_ids[record["id"]]
    claim = record["claim"].to_s
    terms.any? { |term| alignment_term_present?(claim, term) }
  end
end

def validate_bridge_presentation(model, index, sources, visible_items, errors)
  return if index.nil?
  return unless model.dig("target", "mode") == "job-targeted"

  requirements = Array(model.dig("alignment", "requirements"))
    .select { |entry| entry.is_a?(Hash) && entry["status"] == "matched" }

  Array(index["evidence_bridges"]).each do |bridge|
    next unless bridge.is_a?(Hash)
    profile_ref = bridge["profile_ref"].to_s
    record_refs = Array(bridge["records"]).map(&:to_s)
    phrases = Array(bridge["required_public_phrases"]).map(&:to_s).reject(&:empty?)
    next if profile_ref.empty? || record_refs.empty? || phrases.empty?

    bridge_alias_text = Array(bridge["aliases"]).join(" ")
    active = requirements.any? do |requirement|
      aliases = Array(requirement["aliases"])
      refs = Array(requirement["evidence_refs"]).map(&:to_s)
      aliases.any? { |term| alignment_term_present?(bridge_alias_text, term.to_s) } &&
        !(refs & ([profile_ref] + record_refs)).empty?
    end
    next unless active

    Array(model["projects"]).each_with_index do |entry, index_position|
      next unless entry.is_a?(Hash)
      prefix = "resume.projects[#{index_position}]"
      entry_items = visible_items.select { |item| item["path"].start_with?(prefix) }
      entry_project_refs = entry_items.flat_map do |item|
        Array(item["refs"]).select { |ref| sources.dig(ref, "origin") == "project" }
      end.uniq
      relevant_records = record_refs & entry_project_refs
      next if relevant_records.empty?

      presented = entry_items.any? do |item|
        next false unless item["path"].start_with?("#{prefix}.details[")
        refs = Array(item["refs"]).map(&:to_s)
        refs.include?(profile_ref) &&
          !(refs & relevant_records).empty? &&
          phrases.all? { |phrase| alignment_term_present?(item["text"].to_s, phrase) }
      end
      next if presented

      label = entry.dig("primary", "text") || "project at index #{index_position}"
      errors << "#{prefix} #{label.inspect} was selected through evidence bridge #{profile_ref}, " \
                "but no project detail co-cites that profile fact and a bridged project record " \
                "while stating #{phrases.map(&:inspect).join(', ')}"
    end
  end
end

def collect_alignment_requirements(model, sources, visible_items, index, errors, warnings)
  return [] unless model["schema_version"] == 1
  alignment = model["alignment"]
  return [] unless alignment.is_a?(Hash) && alignment["requirements"].is_a?(Array)

  visible_text = visible_items.map { |item| item["text"].to_s.downcase }.join(" ")
  selected_refs = visible_items.flat_map { |item| Array(item["refs"]) }.uniq
  prose_items = visible_items.select { |item| prose_item?(item["path"]) }
  prose_refs = prose_items.flat_map { |item| Array(item["refs"]) }.uniq
  prose_text = prose_items.map { |item| item["text"].to_s.downcase }.join(" ")
  coverage_report = []

  alignment["requirements"].each_with_index do |requirement, index_position|
    next unless requirement.is_a?(Hash)
    path = "alignment.requirements[#{index_position}]"
    status = requirement["status"]
    aliases = Array(requirement["aliases"]).reject(&:empty?)
    refs = Array(requirement["evidence_refs"])
    refs.each do |reference|
      source = sources[reference]
      if source.nil?
        errors << "#{path} references missing source #{reference}"
        next
      end
      unless %w[repo-verified user-stated].include?(source["kind"])
        errors << "#{path} uses ineligible kind #{source['kind'].inspect} from #{reference}"
      end
      if source["origin"] == "project" && !%w[led implemented contributed].include?(source["involvement"])
        errors << "#{path} uses ineligible involvement #{source['involvement'].inspect} from #{reference}"
      end
    end
    if status == "matched"
      errors << "#{path} has no alias appearing in public resume text" unless aliases.any? { |alias_name| alignment_term_present?(visible_text, alias_name) }
      errors << "#{path} has no evidence source selected in public resume" if (refs & selected_refs).empty?
    elsif status == "supported_not_selected"
      errors << "#{path} should not use a selected source" unless (refs & selected_refs).empty?
    elsif status == "unsupported"
      errors << "#{path} has an alias that appears in public resume text" if aliases.any? { |alias_name| alignment_term_present?(visible_text, alias_name) }
    end

    coverage = coverage_for(refs, sources, visible_items)
    term = requirement["term"].to_s
    required = requirement["priority"].to_s == "required"
    reason = requirement["selection_reason"].to_s.strip

    candidates = index_candidates(index, aliases)
    unused = candidates.reject { |record| prose_refs.include?(record["id"]) }
      .sort_by { |record| [-record["strength"].to_f, record["project_rank"] || 999] }
    strongest_used = candidates.select { |record| prose_refs.include?(record["id"]) }
      .map { |record| record["strength"].to_f }.max

    # A term the reader actually meets in Summary, Experience, or Selected
    # Projects is on the page, even when the citation behind it is a profile
    # fact. Language and framework requirements land here: Dart is carried by
    # every Flutter bullet and does not need an achievement of its own. Absent
    # from prose entirely is the case worth blocking.
    present_in_prose = aliases.any? { |alias_name| alignment_term_present?(prose_text, alias_name) }
    understated = required && requirement["critical"] && coverage != "demonstrated" && !unused.empty?

    if understated && reason.empty?
      top = unused.first(3).map do |record|
        signals = Array(record["signals"]).join(", ")
        "#{record['id']} (strength #{record['strength']}#{signals.empty? ? '' : ", #{signals}"})"
      end
      message = "#{path} \"#{term}\" is a required requirement covered as #{coverage}, " \
                "but eligible project evidence exists and was not used in Summary, Experience, " \
                "or Selected Projects: #{top.join('; ')}."
      # Only a CRITICAL capability blocks. The 2026-07-29 calibration against the
      # external reviewer's per-skill table showed `stated` scoring 96.7% on
      # average against `demonstrated` at 86.7%, because the stated items were
      # commodity skills (Dart, Git, collaboration) where a Skills listing is
      # exactly what a reviewer expects and no achievement is wanted. Erroring on
      # those produced `selection_reason` boilerplate on two consecutive
      # applications and cost nothing externally to omit.
      #
      # The case this gate was built for still errors: GoShorty's `app
      # performance` was critical, absent from all achievement text, and had a
      # strength-10 before/after measurement sitting unused.
      if requirement["critical"] && !present_in_prose
        errors << "#{message} It is CRITICAL and appears in no achievement text. Use the " \
                  "strongest record or record #{path}.selection_reason"
      elsif present_in_prose
        warnings << "#{message} The term is on the page, so this is a strength choice, not a gap"
      else
        warnings << "#{message} Not critical, so this does not block, but the evidence is there"
      end
    elsif required && coverage == "demonstrated" && !unused.empty? && strongest_used
      best_unused = unused.first
      if best_unused["strength"].to_f - strongest_used >= 3.0
        warnings << "requirement \"#{term}\" is demonstrated by evidence of strength " \
                    "#{strongest_used} while #{best_unused['id']} (strength #{best_unused['strength']}) " \
                    "was available"
      end
    end

    coverage_report << {
      "term" => term,
      "priority" => requirement["priority"],
      "critical" => requirement["critical"],
      "status" => status,
      "coverage" => coverage,
      "in_prose" => present_in_prose,
      "selection_reason" => reason.empty? ? nil : reason,
      # Only carried for requirements that are actually under-covered. Listing
      # them for every requirement would recreate the "258 sources unused" noise.
      "unused_candidates" => understated ? unused.first(3).map { |record| record["id"] } : []
    }
  end
  coverage_report
end

def month_index(value)
  return nil if value.nil? || value.to_s == "present"
  match = value.to_s.match(/\A(\d{4})(?:-(\d{2})(?:-\d{2})?)?\z/)
  return nil unless match
  match[1].to_i * 12 + (match[2] || "1").to_i - 1
end

def timeline_warnings(profile)
  roles = Array(profile["experience"]).filter_map do |entry|
    next unless entry.is_a?(Hash)
    start_month = month_index(entry["start"])
    end_month = entry["end"].to_s == "present" ? 10**9 : month_index(entry["end"])
    next unless start_month && end_month
    {
      "label" => [entry["organization"], entry["title"]].compact.join(" / "),
      "start" => start_month,
      "end" => end_month,
      "employment_type" => entry["employment_type"]
    }
  end.sort_by { |role| role["start"] }

  breaks = Array(profile["career_breaks"]).filter_map do |entry|
    next unless entry.is_a?(Hash)
    start_month = month_index(entry["start"])
    end_month = month_index(entry["end"])
    next unless start_month && end_month
    {"label" => entry["label"] || "confirmed career break", "start" => start_month, "end" => end_month}
  end

  results = []
  coverage = (roles + breaks).sort_by { |entry| entry["start"] }
  previous = coverage.first
  coverage.drop(1).each do |current|
    missing_months = current["start"] - previous["end"] - 1
    if missing_months > 3
      results << "profile timeline has an unexplained gap of #{missing_months} months between #{previous['label']} and #{current['label']}"
    end
    previous = current if current["end"] > previous["end"]
  end
  roles.combination(2) do |first, second|
    next unless first["employment_type"] == "full-time" && second["employment_type"] == "full-time"
    if [first["start"], second["start"]].max <= [first["end"], second["end"]].min
      results << "profile timeline has overlapping full-time roles: #{first['label']} and #{second['label']}"
    end
  end
  results
end

errors = []
warnings = []
sources = {}
visible_items = []

begin
  model = JSON.parse(read_utf8(options[:model]))
rescue JSON::ParserError => e
  warn "cannot parse resume JSON #{options[:model]}: #{e.message}"
  exit 2
end

unless File.file?(options[:profile])
  warn "profile file does not exist: #{options[:profile]}"
  exit 2
end

profile = load_yaml(options[:profile])
collect_profile_sources(profile, sources, errors)
warnings.concat(timeline_warnings(profile))
link_registry = collect_link_registry(profile)

ranking = nil
if options[:ranking] && File.file?(options[:ranking])
  ranking = load_yaml(options[:ranking])
end

# The generated evidence index makes the understatement gate possible. Without
# it the checker can still verify everything it always did, so a missing index
# degrades to a warning rather than blocking a render.
evidence_index = nil
index_path = options[:index]
if index_path.nil?
  default_index = File.join(File.dirname(File.dirname(File.expand_path(options[:profile]))), "index", "evidence-index.yaml")
  index_path = default_index if File.file?(default_index)
end
if index_path && File.file?(index_path)
  evidence_index = load_yaml(index_path)
  # A stale index weakens the understatement gate silently: a project curated
  # after the last rebuild has no rows, so its evidence can never be reported as
  # unused. Compare record counts rather than re-deriving the whole index.
  indexed_ids = Array(evidence_index["records"]).filter_map { |row| row["id"] if row.is_a?(Hash) }.to_set
  curated_ids = Dir.glob(File.join(options[:projects], "*.yaml"))
    .reject { |path| path.end_with?(".candidates.yaml") }
    .flat_map { |path| Array(load_yaml(path)["records"]).filter_map { |record| record["id"] if record.is_a?(Hash) } }
    .to_set
  missing = (curated_ids - indexed_ids).to_a.sort
  unless missing.empty?
    warnings << "evidence index is stale: #{missing.length} curated records are absent from it " \
                "(#{missing.first(5).join(', ')}#{missing.length > 5 ? ', ...' : ''}). " \
                "Run ekb index"
  end
else
  warnings << "no evidence index loaded: the understatement gate is inactive. Run ekb index"
end

project_files = Dir.glob(File.join(options[:projects], "*.yaml"))
  .reject { |path| path.end_with?(".candidates.yaml") }
  .sort

project_files.each do |path|
  project = load_yaml(path)
  project_key = (project["project"] || File.basename(path, ".yaml")).to_s
  Array(project["records"]).each_with_index do |record, index|
    unless record.is_a?(Hash) && record["id"].is_a?(String)
      errors << "#{path} records[#{index}] has no stable ID"
      next
    end
    id = record["id"]
    if sources.key?(id)
      errors << "duplicate source ID #{id} in #{path}"
      next
    end
    sources[id] = {
      "origin" => "project",
      "project" => project_key,
      "kind" => record["kind"],
      "involvement" => normalize_involvement(record),
      "numeric_content" => JSON.generate({
        "statement" => record["statement"],
        "reasoning" => record["reasoning"],
        "limitations" => record["limitations"],
        "interview_notes" => record["interview_notes"],
        "evidence_notes" => Array(record["evidence"]).map { |item| item.is_a?(Hash) ? item["note"] : nil }.compact
      })
    }
  end
end

collect_visible_items(model, visible_items, errors)
errors << "resume model contains no sourced visible items" if visible_items.empty?

internal_label = /\b(repo-verified|user-stated|inferred|source_ref|provisional inference)\b/i

composed_items = 0

visible_items.each do |item|
  text = item["text"]
  refs = Array(item["refs"])
  next unless text.is_a?(String) && !refs.empty?
  composed_items += 1 if refs.length > 1

  if text.match?(internal_label)
    errors << "#{item['path']} exposes an internal provenance label"
  end

  resolved = refs.filter_map do |ref|
    source = sources[ref]
    errors << "#{item['path']} references missing source #{ref}" if source.nil?
    source && [ref, source]
  end
  next if resolved.empty?

  # Every source in a composition must clear the same bar on its own. There is
  # no averaging: composing two weak sources does not produce a strong claim.
  resolved.each do |(ref, source)|
    unless %w[repo-verified user-stated].include?(source["kind"])
      errors << "#{item['path']} uses ineligible kind #{source['kind'].inspect} from #{ref}"
    end
    next unless source["origin"] == "project"
    unless %w[led implemented contributed].include?(source["involvement"])
      errors << "#{item['path']} uses ineligible involvement #{source['involvement'].inspect} from #{ref}"
    end
  end

  # The strictest involvement governs the wording. If any cited record is only
  # `contributed`, the composed sentence may not claim leadership or sole
  # authorship, even when a co-cited record would allow it on its own.
  weakest = resolved.map { |(_ref, source)| source["involvement"] }.compact
  if weakest.include?("contributed") &&
     text.match?(/\b(led\s+(?!to\b)|owned end[- ]to[- ]end|single-handedly|solely)\b/i)
    contributed = resolved.select { |(_ref, source)| source["involvement"] == "contributed" }
                          .map { |(ref, _source)| ref }
    errors << "#{item['path']} overstates contributed source #{contributed.join(', ')}"
  end

  # Profile-backed text must be supported by the union of the cited entries, so
  # a composed line may draw wording from several confirmed facts at once.
  profile_sources = resolved.select { |(_ref, source)| source["origin"] == "profile" }
  if profile_sources.length == resolved.length
    union = profile_sources.flat_map { |(_ref, source)| Array(source["profile_values"]) }
    unless profile_supports_text?(text, union)
      errors << "#{item['path']} is not supported by confirmed profile values in " \
                "#{profile_sources.map(&:first).join(', ')}"
    end
  end

  # A number needs one source that carries it. Composition may not assemble a
  # figure that none of its sources states.
  supported_numbers = resolved.flat_map do |(_ref, source)|
    numeric_tokens(source["numeric_content"]).map { |token| canonical_numeric_token(token) }
  end
  numeric_tokens(text).uniq.each do |number|
    canonical = canonical_numeric_token(number)
    unless supported_numbers.include?(canonical)
      errors << "#{item['path']} contains unsupported number #{number.inspect} for #{refs.join(', ')}"
    end
  end

  supported_words = resolved.flat_map { |(_ref, source)| word_number_tokens(source["numeric_content"]) }.uniq
  word_number_tokens(text).uniq.each do |word|
    next if supported_words.include?(word)
    errors << "#{item['path']} contains unsupported spelled number #{word.inspect} for #{refs.join(', ')}"
  end
end

coverage_report = collect_alignment_requirements(model, sources, visible_items, evidence_index, errors, warnings)

# The shortlist lives beside the frozen application unless pointed elsewhere.
shortlist = nil
shortlist_path = options[:shortlist]
if shortlist_path.nil? && model["application_id"]
  default_shortlist = File.join(
    File.dirname(File.dirname(File.expand_path(options[:profile]))),
    "applications", "#{model['application_id']}.evidence.yaml"
  )
  shortlist_path = default_shortlist if File.file?(default_shortlist)
end
if shortlist_path && File.file?(shortlist_path)
  shortlist = load_yaml(shortlist_path)
  prose_refs_for_shortlist = visible_items
    .select { |item| prose_item?(item["path"]) }
    .flat_map { |item| Array(item["refs"]) }
    .uniq
  visible_refs_for_shortlist = visible_items.flat_map { |item| Array(item["refs"]) }.uniq
  shortlist_findings(shortlist, prose_refs_for_shortlist, visible_refs_for_shortlist, errors, warnings)
elsif model.dig("target", "mode") == "job-targeted"
  warnings << "no evidence shortlist for this application: selection is unrecorded. " \
              "Run ekb shortlist #{model['application_id']}"
end

validate_bridge_presentation(model, evidence_index, sources, visible_items, errors)
check_model_links(model, link_registry, errors)
check_summary_project_links(visible_items, sources, link_registry, errors, warnings)
warnings.concat(organization_link_warnings(model, link_registry))

selected_projects = visible_items
  .flat_map { |item| Array(item["refs"]).filter_map { |ref| sources.dig(ref, "project") } }
  .uniq
selected_projects_section = visible_items
  .select { |item| item["path"].start_with?("resume.projects[") }
  .flat_map { |item| Array(item["refs"]).filter_map { |ref| sources.dig(ref, "project") } }
  .uniq
section_entry_projects = Array(model["projects"]).each_with_index.filter_map do |_entry, index|
  prefix = "resume.projects[#{index}]"
  projects_for_entry = visible_items
    .select { |item| item["path"].start_with?(prefix) }
    .flat_map { |item| Array(item["refs"]).filter_map { |ref| sources.dig(ref, "project") } }
    .uniq
  if projects_for_entry.empty?
    errors << "#{prefix} does not resolve to a curated project"
    nil
  elsif projects_for_entry.length > 1
    errors << "#{prefix} mixes sources from multiple projects: #{projects_for_entry.sort.join(', ')}"
    nil
  else
    projects_for_entry.first
  end
end
if section_entry_projects.uniq.length < 2
  errors << "Selected Projects must contain at least two distinct curated projects"
end

# --- Engagements inside a role ---------------------------------------------
#
# A named engagement is a client project rendered under its employer, so it
# carries the two invariants the Selected Projects section already has, plus one
# more that only applies here: the project must actually belong to that
# employer. profile.yaml records the association, and blending a project into
# the wrong company block is exactly what profile-constraint-002 forbids.

employer_projects = Array(profile["experience"]).each_with_object({}) do |entry, memo|
  next unless entry.is_a?(Hash)
  memo[entry["organization"].to_s] = Array(entry["projects"]).map(&:to_s)
end
standalone = Array(profile.dig("preferences", "standalone_projects")).map(&:to_s)
academic = Array(profile.dig("preferences", "academic_projects")).map(&:to_s)

Array(model["experience"]).each_with_index do |entry, entry_index|
  next unless entry.is_a?(Hash)
  organization = entry.dig("organization", "text").to_s
  Array(entry["engagements"]).each_with_index do |_engagement, position|
    prefix = "resume.experience[#{entry_index}].engagements[#{position}]"
    projects_for_engagement = visible_items
      .select { |item| item["path"].start_with?(prefix) }
      .flat_map { |item| Array(item["refs"]).filter_map { |ref| sources.dig(ref, "project") } }
      .uniq
    if projects_for_engagement.empty?
      errors << "#{prefix} does not resolve to a curated project"
      next
    end
    if projects_for_engagement.length > 1
      errors << "#{prefix} mixes sources from multiple projects: #{projects_for_engagement.sort.join(', ')}"
      next
    end
    project = projects_for_engagement.first
    allowed = employer_projects[organization]
    if allowed && !allowed.include?(project)
      errors << "#{prefix} places project #{project} under #{organization}, which profile.yaml " \
                "does not associate with that employer"
    end
    if standalone.include?(project)
      errors << "#{prefix} places independent project #{project} under Experience; " \
                "preferences.standalone_projects keeps it out of employment history"
    end
    if academic.include?(project)
      errors << "#{prefix} places academic project #{project} under Experience; " \
                "it belongs with its education entry"
    end
  end
end
selected_project_labels = Array(model["projects"]).filter_map do |entry|
  entry.dig("primary", "text") if entry.is_a?(Hash)
end

eligible_projects = sources.values
  .select do |source|
    source["origin"] == "project" &&
      %w[repo-verified user-stated].include?(source["kind"]) &&
      %w[led implemented contributed].include?(source["involvement"])
  end
  .map { |source| source["project"] }
  .uniq

selected_ranks = {}
if ranking
  Array(ranking["projects"]).each do |entry|
    next unless entry.is_a?(Hash)
    selected_ranks[entry["project"].to_s] = entry["rank"] if selected_projects.include?(entry["project"].to_s)
  end
  # Projects that own evidence a required requirement could have used. A skipped
  # project outside this set was skipped correctly.
  relevant_projects = nil
  if evidence_index
    record_projects = Array(evidence_index["records"])
      .select { |record| record.is_a?(Hash) }
      .to_h { |record| [record["id"].to_s, record["project"].to_s] }
    relevant_projects = coverage_report
      .select { |entry| entry["priority"].to_s == "required" }
      .flat_map { |entry| entry["unused_candidates"] }
      .filter_map { |id| record_projects[id.to_s] }
      .uniq
  end
  warnings.concat(
    rank_warnings(ranking, selected_projects, eligible_projects, model.dig("target", "mode"), relevant_projects)
  )
end

ordered_projects = selected_projects.sort_by { |project| selected_ranks[project] || 999 }
ordered_section_projects = selected_projects_section.sort_by { |project| selected_ranks[project] || 999 }

# "N of 262 sources were not selected" is true of every resume ever generated
# here and tells nobody anything. What is worth surfacing is unused evidence
# that a REQUIRED requirement could have used, which the coverage pass already
# computed.
unused_for_required = coverage_report
  .select { |entry| entry["priority"].to_s == "required" }
  .flat_map { |entry| entry["unused_candidates"] }
  .uniq
unless unused_for_required.empty?
  warnings << "#{unused_for_required.length} eligible records supporting required requirements " \
              "were not used: #{unused_for_required.sort.join(', ')}"
end

coverage_counts = coverage_report.group_by { |entry| entry["coverage"] }
  .transform_values(&:length)
stated_required = coverage_report.select do |entry|
  entry["priority"].to_s == "required" && entry["critical"] && entry["coverage"] == "stated"
end
unless stated_required.empty?
  warnings << "required requirements carried by a claim rather than an achievement: " \
              "#{stated_required.map { |entry| entry['term'] }.join(', ')}"
end

# Selection rubric. It ships with the toolkit rather than the workspace: it
# describes how well a resume used the evidence available to it, which is a
# property of the procedure, not of any one person's career.
rubric = nil
rubric_path = options[:rubric]
if rubric_path.nil?
  default_rubric = File.join(
    File.dirname(File.dirname(File.expand_path(__FILE__))), "config", "review-rubric.json"
  )
  rubric_path = default_rubric if File.file?(default_rubric)
end
if rubric_path && File.file?(rubric_path)
  begin
    rubric = JSON.parse(read_utf8(rubric_path))
  rescue JSON::ParserError => e
    warnings << "cannot parse selection rubric #{rubric_path}: #{e.message}"
  end
end
score = selection_score(rubric, coverage_report, shortlist)
signals = external_signals(model, profile, coverage_report)

report = {
  "valid" => errors.empty?,
  "checks" => {
    "project_files" => project_files.length,
    "available_sources" => sources.length,
    "visible_items" => visible_items.length,
    "registered_links" => link_registry["allowed"].length,
    "ranking_loaded" => !ranking.nil?,
    "evidence_index_loaded" => !evidence_index.nil?,
    "composed_items" => composed_items
  },
  "errors" => errors,
  "warnings" => warnings,
  "coverage" => {
    "counts" => coverage_counts,
    "requirements" => coverage_report
  },
  "selection_score" => score,
  "external_signals" => signals,
  "selected_sources" => visible_items.flat_map { |item| Array(item["refs"]) }.compact.uniq.sort,
  "project_selection" => {
    "selected" => ordered_projects,
    "ranks" => ordered_projects.map { |project| selected_ranks[project] }.compact,
    "evidence_used" => ordered_projects,
    "evidence_ranks" => ordered_projects.map { |project| selected_ranks[project] }.compact,
    "named_in_selected_projects" => ordered_section_projects,
    "named_ranks" => ordered_section_projects.map { |project| selected_ranks[project] }.compact,
    "named_labels" => selected_project_labels
  }
}

puts JSON.pretty_generate(report)
exit(errors.empty? ? 0 : 1)
