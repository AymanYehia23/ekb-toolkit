#!/usr/bin/env ruby
#
# Coverage-strength and understatement-gate tests.
#
# These exercise scripts/resume_source_check.rb directly rather than through
# scripts/resume_render.py, so they run without the document and PDF rendering
# dependencies. The behaviour under test is evidence selection, not rendering.

require "fileutils"
require "json"
require "minitest/autorun"
require "open3"
require "tmpdir"
require "yaml"

class ResumeCoverageTest < Minitest::Test
  ROOT = File.expand_path("..", __dir__)
  CHECKER = File.join(ROOT, "scripts", "resume_source_check.rb")
  INDEXER = File.join(ROOT, "scripts", "ekb_index.py")
  SHORTLISTER = File.join(ROOT, "scripts", "ekb_shortlist.py")

  # A small self-contained knowledge base: one capability (`performance`) with a
  # strong unused record, and one profile skill that merely claims it.
  PROJECT_YAML = <<~YAML
    project: sample
    repo: /read-only/sample
    analyses: []
    records:
      - id: sample-001
        statement: >
          Executed a Flutter rendering and memory optimization pass, converting
          eager grid maps to lazy builders and removing a blocking connectivity
          probe from every request.
        kind: repo-verified
        involvement: implemented
        evidence:
          - path: lib/perf.dart
            at: aaa111
        reasoning: The branch contains the optimization commits.
        limitations: No release-mode measurement exists.
        tags: [flutter, performance, rendering]
      - id: sample-002
        statement: >
          Built a checkout flow with server-confirmed payment status.
        kind: repo-verified
        involvement: implemented
        evidence:
          - path: lib/checkout.dart
            at: bbb222
        reasoning: The repository contains the checkout implementation.
        limitations: No conversion result is claimed.
        tags: [flutter, checkout, payments]
      - id: sample-003
        statement: >
          Decomposed a cart controller from 946 to 177 lines across a 48-file
          change.
        kind: repo-verified
        involvement: implemented
        evidence:
          - path: lib/cart.dart
            at: ccc444
        reasoning: The repository contains the structural refactor.
        limitations: Code-size counts are private evidence, not public impact.
        tags: [flutter, refactoring]
      - id: sample-004
        statement: >
          Delivered a Flutter proof of concept in 3 days.
        kind: user-stated
        involvement: implemented
        evidence:
          - path: context/sample-questions.md
            at: Q1
        reasoning: The duration was confirmed by the user.
        limitations: This was a proof of concept, not a production release.
        tags: [flutter, delivery]
  YAML

  # A second project exists only so the mandatory two-entry Selected Projects
  # section can be satisfied; it carries no `performance` evidence.
  OTHER_YAML = <<~YAML
    project: other
    repo: /read-only/other
    analyses: []
    records:
      - id: other-001
        statement: >
          Implemented an offline request queue that replays writes once
          connectivity returns.
        kind: repo-verified
        involvement: implemented
        evidence:
          - path: lib/queue.dart
            at: ccc333
        reasoning: The repository contains the queue and its replay path.
        limitations: No production reliability result is claimed.
        tags: [flutter, offline]
      - id: other-002
        statement: >
          Built a localized settings screen supporting Arabic and English.
        kind: repo-verified
        involvement: implemented
        evidence:
          - path: lib/settings.dart
            at: ddd444
        reasoning: The repository contains both locale files.
        limitations: No adoption result is claimed.
        tags: [flutter, localization]
  YAML

  PROFILE_YAML = <<~YAML
    schema_version: 1
    identity:
      id: profile-identity-001
      value: Test Person
      kind: user-stated
    contact:
      - id: profile-contact-001
        type: email
        value: test@example.com
        label: test@example.com
        kind: user-stated
    experience:
      - id: profile-experience-001
        organization: Example Ltd
        title: Mobile Engineer
        start: 2024-06
        end: present
        kind: user-stated
        projects:
          - sample
    skills:
      - id: profile-skill-001
        group: Engineering practices
        kind: repo-verified
        items:
          - name: Performance and memory optimization
            depth: exposure
            basis: "1 project"
    responsibilities:
      - id: profile-responsibility-ai-001
        label: AI-assisted engineering
        kind: user-stated
        value: Uses AI agents throughout proof-of-concept builds.
        phrasings:
          - Uses AI agents throughout proof-of-concept builds.
        evidence_bridges:
          - aliases: [AI agents, AI-assisted]
            records: [sample-004]
            required_public_phrases: [proof-of-concept, AI agents, 3 days]
            cap: The proof-of-concept qualifier must travel with the claim.
    project_links:
      - project: sample
        link_status: confirmed
        kind: user-stated
      - project: other
        link_status: confirmed
        kind: user-stated
  YAML

  def with_workspace
    Dir.mktmpdir("ekb-coverage-") do |dir|
      FileUtils.mkdir_p(File.join(dir, "projects"))
      FileUtils.mkdir_p(File.join(dir, "profile"))
      File.write(File.join(dir, "projects", "sample.yaml"), PROJECT_YAML)
      File.write(File.join(dir, "projects", "other.yaml"), OTHER_YAML)
      File.write(File.join(dir, "profile", "profile.yaml"), PROFILE_YAML)
      _out, err, status = Open3.capture3("python3", INDEXER, "--root", dir)
      raise "indexer failed: #{err}" unless status.success?
      yield dir
    end
  end

  # A resume whose Experience demonstrates checkout but only *claims*
  # performance through the skills list. This is the shape that used to pass.
  def base_model(performance_status: "matched")
    {
      "schema_version" => 1,
      "application_id" => "test",
      "target" => {"mode" => "job-targeted", "summary_lead" => "Mobile Engineer"},
      "basics" => {
        "name" => {"text" => "Test Person", "source_ref" => "profile-identity-001"},
        "contact" => [{"text" => "test@example.com", "source_ref" => "profile-contact-001"}]
      },
      "summary" => [],
      "experience" => [{
        "organization" => {"text" => "Example Ltd", "source_ref" => "profile-experience-001"},
        "title" => {"text" => "Mobile Engineer", "source_ref" => "profile-experience-001"},
        "start" => {"text" => "Jun 2024", "source_ref" => "profile-experience-001"},
        "end" => {"text" => "Present", "source_ref" => "profile-experience-001"},
        "bullets" => [
          {"text" => "Built a checkout flow with server-confirmed payment status.",
           "source_ref" => "sample-002"}
        ]
      }],
      "projects" => [
        {"primary" => {"text" => "Sample Checkout", "source_ref" => "sample-002"},
         "details" => [
           {"text" => "Built a checkout flow with server-confirmed payment status.",
            "source_ref" => "sample-002"}
         ]},
        {"primary" => {"text" => "Other App", "source_ref" => "other-001"},
         "details" => [
           {"text" => "Implemented an offline request queue that replays writes once connectivity returns.",
            "source_ref" => "other-001"}
         ]}
      ],
      "skills" => [{
        "name" => "Engineering practices",
        "items" => [
          {"text" => "Performance and memory optimization", "source_ref" => "profile-skill-001"}
        ]
      }],
      "alignment" => {
        "requirements" => [
          {"term" => "app performance", "aliases" => ["performance"],
           "priority" => "required", "critical" => true,
           "status" => performance_status, "evidence_refs" => ["profile-skill-001"]}
        ]
      }
    }
  end

  def check(dir, model)
    path = File.join(dir, "model.json")
    File.write(path, JSON.pretty_generate(model))
    stdout, stderr, status = Open3.capture3(
      "ruby", CHECKER,
      "--model", path,
      "--profile", File.join(dir, "profile", "profile.yaml"),
      "--projects", File.join(dir, "projects"),
      "--index", File.join(dir, "index", "evidence-index.yaml")
    )
    raise "checker produced no output: #{stderr}" if stdout.strip.empty?
    [JSON.parse(stdout), status]
  end

  def test_index_ranks_the_performance_record_under_its_capability
    with_workspace do |dir|
      index = YAML.safe_load(File.read(File.join(dir, "index", "evidence-index.yaml")))
      assert_includes index["capabilities"]["performance"], "sample-001"
      row = index["records"].find { |record| record["id"] == "sample-001" }
      assert row["eligible"]
      assert_equal "implemented", row["involvement"]
    end
  end

  def test_index_and_shortlist_surface_record_limitations_as_selection_cautions
    with_workspace do |dir|
      index = YAML.safe_load(File.read(File.join(dir, "index", "evidence-index.yaml")))
      row = index["records"].find { |record| record["id"] == "sample-001" }
      assert_includes row["cautions"], "No release-mode measurement exists."

      FileUtils.mkdir_p(File.join(dir, "applications"))
      File.write(File.join(dir, "applications", "test.yaml"), <<~YAML)
        schema_version: 1
        id: test
        targeting:
          requirements:
            - term: app performance
              aliases: [performance]
              priority: required
              critical: true
      YAML
      _out, err, status = Open3.capture3(
        "python3", SHORTLISTER, "--root", dir, "--application", "test"
      )
      assert status.success?, err
      shortlist = YAML.safe_load(
        File.read(File.join(dir, "applications", "test.evidence.yaml"))
      )
      candidate = shortlist["requirements"].first["candidates"].find do |entry|
        entry["ref"] == "sample-001"
      end
      refute_nil candidate
      assert_includes candidate["cautions"], "No release-mode measurement exists."
    end
  end

  def test_index_distinguishes_material_duration_from_gameable_code_size
    with_workspace do |dir|
      index = YAML.safe_load(File.read(File.join(dir, "index", "evidence-index.yaml")))
      rows = index["records"].to_h { |record| [record["id"], record] }
      refute_includes rows["sample-003"]["signals"], "measured"
      assert_includes rows["sample-004"]["signals"], "measured"
    end
  end

  def test_profile_bridge_makes_target_attribute_retrieve_the_project_record
    with_workspace do |dir|
      index = YAML.safe_load(File.read(File.join(dir, "index", "evidence-index.yaml")))
      bridge = index["evidence_bridges"].find do |entry|
        entry["profile_ref"] == "profile-responsibility-ai-001"
      end
      refute_nil bridge
      assert_includes bridge["records"], "sample-004"

      model = base_model
      model["alignment"]["requirements"][0]["selection_reason"] =
        "Keep this fixture focused on the AI evidence bridge."
      model["summary"] << {
        "text" => "Uses AI agents throughout proof-of-concept builds.",
        "source_ref" => "profile-responsibility-ai-001"
      }
      model["alignment"]["requirements"] << {
        "term" => "AI coding tools", "aliases" => ["AI agents"],
        "priority" => "required", "critical" => true,
        "status" => "matched", "evidence_refs" => ["profile-responsibility-ai-001"]
      }
      report, status = check(dir, model)
      assert status.success?, "the profile line keeps this a strength choice rather than a gap"
      assert(
        report["warnings"].any? { |warning| warning.include?("sample-004") },
        "the bridged record must be named: #{report['warnings']}"
      )
    end
  end

  def bridged_project_model
    model = base_model
    model["alignment"]["requirements"][0]["selection_reason"] =
      "Keep this fixture focused on the AI evidence bridge."
    model["summary"] << {
      "text" => "Uses AI agents throughout proof-of-concept builds.",
      "source_ref" => "profile-responsibility-ai-001"
    }
    model["projects"][0] = {
      "primary" => {"text" => "Sample AI POC", "source_ref" => "sample-004"},
      "details" => [{
        "text" => "Delivered a Flutter proof of concept in 3 days.",
        "source_ref" => "sample-004"
      }]
    }
    model["alignment"]["requirements"] << {
      "term" => "AI coding tools", "aliases" => ["AI agents"],
      "priority" => "required", "critical" => true,
      "status" => "matched",
      "evidence_refs" => ["profile-responsibility-ai-001", "sample-004"]
    }
    model
  end

  def test_bridge_rejects_a_selected_project_that_hides_its_selection_reason
    with_workspace do |dir|
      report, status = check(dir, bridged_project_model)
      refute status.success?
      assert(
        report["errors"].any? do |error|
          error.include?("selected through evidence bridge") &&
            error.include?("proof-of-concept") &&
            error.include?("AI agents") &&
            error.include?("3 days")
        end,
        report["errors"].inspect
      )
    end
  end

  def test_bridge_accepts_a_co_cited_project_detail_with_required_phrases
    with_workspace do |dir|
      model = bridged_project_model
      model["projects"][0]["details"][0] = {
        "text" => "Built this Flutter proof-of-concept with AI agents in 3 days.",
        "source_refs" => ["profile-responsibility-ai-001", "sample-004"]
      }
      report, status = check(dir, model)
      assert status.success?, report["errors"].inspect
    end
  end

  def test_skills_only_coverage_of_a_required_requirement_is_an_error
    with_workspace do |dir|
      report, status = check(dir, base_model)
      refute status.success?, "a skills-only required requirement must not pass"
      assert_equal "stated", report.dig("coverage", "requirements", 0, "coverage")
      assert(
        report["errors"].any? { |error| error.include?("sample-001") },
        "the unused stronger record must be named: #{report['errors']}"
      )
    end
  end

  def test_moving_the_evidence_into_a_bullet_resolves_the_gate
    with_workspace do |dir|
      model = base_model
      model["experience"][0]["bullets"] << {
        "text" => "Executed a Flutter rendering and memory optimization pass, " \
                  "removing a blocking connectivity probe from every request.",
        "source_ref" => "sample-001"
      }
      model["alignment"]["requirements"][0]["evidence_refs"] = ["sample-001"]
      report, status = check(dir, model)
      assert status.success?, "errors: #{report['errors']}"
      assert_equal "demonstrated", report.dig("coverage", "requirements", 0, "coverage")
    end
  end

  def test_a_recorded_selection_reason_permits_the_omission
    with_workspace do |dir|
      model = base_model
      model["alignment"]["requirements"][0]["selection_reason"] =
        "One page budget; the checkout bullet covers the higher-priority requirement."
      report, status = check(dir, model)
      assert status.success?, "errors: #{report['errors']}"
      assert_equal "stated", report.dig("coverage", "requirements", 0, "coverage")
    end
  end

  def test_a_term_present_in_prose_is_a_warning_not_an_error
    with_workspace do |dir|
      model = base_model
      # The requirement term appears in an achievement bullet even though the
      # citation behind it is a different record. Language and framework
      # requirements behave this way and must not block a render.
      model["experience"][0]["bullets"][0]["text"] =
        "Built a checkout flow with server-confirmed payment status and steady performance."
      report, status = check(dir, model)
      assert status.success?, "errors: #{report['errors']}"
      assert(
        report["warnings"].any? { |warning| warning.include?("sample-001") },
        "the choice should still be surfaced: #{report['warnings']}"
      )
    end
  end

  def test_a_non_critical_requirement_does_not_block
    with_workspace do |dir|
      # Narrowed 2026-07-29: only a CRITICAL capability blocks. Calibration
      # showed commodity skills graded `stated` cost nothing externally. They
      # must not emit an understatement warning either, because that warning
      # pressures the author to publish a low-value matching anecdote.
      model = base_model
      model["alignment"]["requirements"][0]["critical"] = false
      report, status = check(dir, model)
      assert status.success?, "errors: #{report['errors']}"
      refute(
        report["warnings"].any? { |w| w.include?("sample-001") },
        "non-critical stated coverage must not promote a matching project record: #{report['warnings']}"
      )
    end
  end

  def test_a_preferred_requirement_does_not_block
    with_workspace do |dir|
      model = base_model
      model["alignment"]["requirements"][0]["priority"] = "preferred"
      report, status = check(dir, model)
      assert status.success?, "errors: #{report['errors']}"
    end
  end

  def test_missing_index_degrades_to_a_warning
    with_workspace do |dir|
      path = File.join(dir, "model.json")
      File.write(path, JSON.pretty_generate(base_model))
      stdout, _stderr, status = Open3.capture3(
        "ruby", CHECKER,
        "--model", path,
        "--profile", File.join(dir, "profile", "profile.yaml"),
        "--projects", File.join(dir, "projects"),
        "--index", File.join(dir, "nope.yaml")
      )
      report = JSON.parse(stdout)
      assert status.success?, "a missing index must not block: #{report['errors']}"
      refute report["checks"]["evidence_index_loaded"]
      assert(report["warnings"].any? { |warning| warning.include?("understatement gate is inactive") })
    end
  end

  def test_non_ascii_resume_text_is_readable
    with_workspace do |dir|
      model = base_model
      model["alignment"]["requirements"][0]["selection_reason"] = "Budget: 40 EUR is not a claim."
      model["experience"][0]["bullets"][0]["text"] =
        "Built a checkout flow with server-confirmed payment status in euros."
      report, _status = check(dir, model)
      refute_nil report["valid"]
    end
  end

  # --- Evidence shortlist and selection score -------------------------------

  SHORTLIST = <<~YAML
    schema_version: 1
    kind: evidence-shortlist
    application: test
    requirements:
      - term: app performance
        priority: required
        critical: false
        aliases: [performance]
        candidates:
          - ref: sample-001
            project: sample
            strength: 5.0
            signals: []
            claim: a performance pass
          - ref: other-001
            project: other
            strength: 2.0
            signals: []
            claim: an offline queue
        selected: [sample-001]
        reason: strongest available
  YAML

  def write_shortlist(dir, body = SHORTLIST)
    path = File.join(dir, "shortlist.yaml")
    File.write(path, body)
    path
  end

  def check_with_shortlist(
    dir,
    model,
    shortlist_body = SHORTLIST,
    rubric_path = File.join(ROOT, "config", "review-rubric.json")
  )
    path = File.join(dir, "model.json")
    File.write(path, JSON.pretty_generate(model))
    stdout, stderr, status = Open3.capture3(
      "ruby", CHECKER,
      "--model", path,
      "--profile", File.join(dir, "profile", "profile.yaml"),
      "--projects", File.join(dir, "projects"),
      "--index", File.join(dir, "index", "evidence-index.yaml"),
      "--shortlist", write_shortlist(dir, shortlist_body),
      "--rubric", rubric_path
    )
    raise "checker produced no output: #{stderr}" if stdout.strip.empty?
    [JSON.parse(stdout), status]
  end

  def model_using_the_performance_record
    model = base_model
    model["experience"][0]["bullets"] << {
      "text" => "Executed a Flutter rendering and memory optimization pass, " \
                "removing a blocking connectivity probe from every request.",
      "source_ref" => "sample-001"
    }
    model["alignment"]["requirements"][0]["evidence_refs"] = ["sample-001"]
    model
  end

  def test_shortlist_decision_consistent_with_the_document_passes
    with_workspace do |dir|
      report, status = check_with_shortlist(dir, model_using_the_performance_record)
      assert status.success?, "errors: #{report['errors']}"
      refute(report["warnings"].any? { |w| w.include?("shortlist") }, report["warnings"].inspect)
    end
  end

  def test_non_critical_profile_selection_does_not_promote_a_project_anecdote
    with_workspace do |dir|
      model = base_model
      model["alignment"]["requirements"][0]["critical"] = false
      shortlist = <<~YAML
        schema_version: 1
        kind: evidence-shortlist
        application: test
        requirements:
          - term: app performance
            priority: required
            critical: false
            aliases: [performance]
            candidates:
              - ref: sample-001
                project: sample
                strength: 5.0
                signals: []
                claim: a matching project anecdote
            profile_candidates:
              - ref: profile-skill-001
                origin: skill-group
                label: Engineering practices
            selected: [profile-skill-001]
            reason: Non-critical skill is correctly stated; the project record is not independently worth another bullet.
      YAML

      report, status = check_with_shortlist(dir, model, shortlist)
      assert status.success?, "errors: #{report['errors']}"
      refute(
        report["warnings"].any? { |warning| warning.include?("sample-001") },
        "the unused project match must not be treated as a resume gap: #{report['warnings']}"
      )
      assert_equal 100, report.dig("selection_score", "dimensions", "required_coverage", "value")
      gap = report.dig("external_signals", "keyword_gap") || []
      refute gap.any? { |entry| entry["term"] == "app performance" },
             "a supported non-critical skill is not a keyword gap"
    end
  end

  def test_legacy_required_demonstrated_rubric_uses_expected_depth_semantics
    with_workspace do |dir|
      model = base_model
      model["alignment"]["requirements"][0]["critical"] = false
      legacy_rubric = JSON.parse(File.read(File.join(ROOT, "config", "review-rubric.json")))
      dimension = legacy_rubric["dimensions"].delete("required_coverage")
      legacy_rubric["dimensions"]["required_demonstrated"] = dimension
      rubric_path = File.join(dir, "legacy-review-rubric.json")
      File.write(rubric_path, JSON.pretty_generate(legacy_rubric))

      report, status = check_with_shortlist(dir, model, SHORTLIST, rubric_path)
      assert status.success?, "errors: #{report['errors']}"
      assert_equal 100,
                   report.dig("selection_score", "dimensions", "required_coverage", "value")
      refute report.dig("selection_score", "dimensions").key?("required_demonstrated")
    end
  end

  def test_a_required_requirement_with_no_recorded_decision_is_an_error
    with_workspace do |dir|
      undecided = SHORTLIST.sub("selected: [sample-001]", "selected: []")
                           .sub("reason: strongest available", "reason: ''")
      report, status = check_with_shortlist(dir, model_using_the_performance_record, undecided)
      refute status.success?
      assert(
        report["errors"].any? { |e| e.include?("no decision for required requirements") },
        report["errors"].inspect
      )
    end
  end

  def test_a_selection_the_resume_never_cites_is_warned
    with_workspace do |dir|
      # The shortlist says sample-001 won, but the resume never uses it.
      report, _status = check_with_shortlist(dir, base_model)
      assert(
        report["warnings"].any? { |w| w.include?("does not") && w.include?("sample-001") },
        report["warnings"].inspect
      )
    end
  end

  def test_skipping_the_strongest_candidate_without_a_reason_is_warned
    with_workspace do |dir|
      skipped = SHORTLIST.sub("selected: [sample-001]", "selected: [other-001]")
                         .sub("reason: strongest available", "reason: ''")
      model = base_model
      model["experience"][0]["bullets"] << {
        "text" => "Implemented an offline request queue that replays writes once connectivity returns.",
        "source_ref" => "other-001"
      }
      report, _status = check_with_shortlist(dir, model, skipped)
      assert(
        report["warnings"].any? { |w| w.include?("skips its strongest candidate") },
        report["warnings"].inspect
      )
    end
  end

  def test_selection_score_excludes_requirements_with_no_evidence
    with_workspace do |dir|
      model = model_using_the_performance_record
      model["alignment"]["requirements"] << {
        "term" => "insurtech", "aliases" => ["insurtech"], "priority" => "required",
        "critical" => true, "status" => "unsupported", "evidence_refs" => []
      }
      report, _status = check_with_shortlist(dir, model)
      score = report["selection_score"]
      refute_nil score
      assert_equal 1, score["excluded_no_evidence"],
                   "a requirement with no eligible evidence must not be scored"
      assert score["score"] > 50, "score was #{score['score']}"
    end
  end

  # The rubric ships with the toolkit rather than the workspace, because it
  # describes how well a resume used its evidence, which is a property of the
  # procedure and not of any one person's career. So it is found by default.
  def test_selection_score_uses_the_shipped_rubric_by_default
    with_workspace do |dir|
      report, _status = check(dir, model_using_the_performance_record)
      refute_nil report["selection_score"]
      assert_equal 1, report["selection_score"]["rubric_version"]
    end
  end

  def test_selection_score_is_absent_when_the_rubric_path_is_wrong
    with_workspace do |dir|
      path = File.join(dir, "model.json")
      File.write(path, JSON.pretty_generate(model_using_the_performance_record))
      stdout, stderr, _status = Open3.capture3(
        "ruby", CHECKER,
        "--model", path,
        "--profile", File.join(dir, "profile", "profile.yaml"),
        "--projects", File.join(dir, "projects"),
        "--index", File.join(dir, "index", "evidence-index.yaml"),
        "--rubric", File.join(dir, "does-not-exist.json")
      )
      raise "checker produced no output: #{stderr}" if stdout.strip.empty?
      assert_nil JSON.parse(stdout)["selection_score"]
    end
  end

  # --- External signals ------------------------------------------------------
  #
  # The separate resume-review prompt weighs seniority and "missing or weakly
  # represented" keywords, both of which the selection score excludes on
  # purpose. These assert the blind spot is reported rather than hidden.

  def test_seniority_gap_is_reported_against_the_confirmed_timeline
    with_workspace do |dir|
      model = model_using_the_performance_record
      model["alignment"]["requirements"] << {
        "term" => "5+ years of professional experience", "aliases" => ["5 years"],
        "priority" => "required", "critical" => true,
        "status" => "unsupported", "evidence_refs" => []
      }
      report, _status = check_with_shortlist(dir, model)
      seniority = report.dig("external_signals", "seniority")
      refute_nil seniority, report["external_signals"].inspect
      assert_equal 5, seniority["required_years"]
      assert_equal "below", seniority["status"],
                   "the fixture profile starts 2024-06, so five years cannot be met"
    end
  end

  def test_keyword_gap_separates_fixable_from_real_gaps
    with_workspace do |dir|
      model = base_model    # performance is `stated` while sample-001 sits unused
      model["alignment"]["requirements"] << {
        "term" => "insurtech", "aliases" => ["insurtech"], "priority" => "preferred",
        "critical" => false, "status" => "unsupported", "evidence_refs" => []
      }
      report, _status = check_with_shortlist(dir, model)
      gap = report.dig("external_signals", "keyword_gap")
      performance = gap.find { |entry| entry["term"] == "app performance" }
      insurtech = gap.find { |entry| entry["term"] == "insurtech" }
      assert performance["fixable"], "evidence exists for it, so it is fixable here"
      refute insurtech["fixable"], "no evidence exists, so it is a real gap"
    end
  end

  def test_seniority_is_absent_when_the_posting_states_no_bar
    with_workspace do |dir|
      report, _status = check_with_shortlist(dir, model_using_the_performance_record)
      assert_nil report.dig("external_signals", "seniority")
    end
  end

  # --- Multi-source composition ---------------------------------------------
  #
  # A claim that is inherently plural, such as a count spanning several apps,
  # cannot be sourced to one record. Composition widens what is sayable without
  # weakening what must be true: every source clears the bar on its own, the
  # strictest involvement governs the wording, and no number may be assembled
  # that none of the sources states.

  def composed_summary(model, refs, text)
    model["summary"] = [{"text" => text, "source_refs" => refs}]
    model
  end

  def test_a_composed_claim_across_two_projects_is_accepted
    with_workspace do |dir|
      model = composed_summary(
        model_using_the_performance_record,
        ["sample-002", "other-001"],
        "Built checkout and offline request queue flows across the Flutter portfolio."
      )
      report, status = check(dir, model)
      assert status.success?, "errors: #{report['errors']}"
      assert_equal 1, report["checks"]["composed_items"]
      assert_includes report["selected_sources"], "other-001"
      assert_includes report["selected_sources"], "sample-002"
    end
  end

  def test_a_number_no_source_states_is_rejected_in_a_composition
    with_workspace do |dir|
      model = composed_summary(
        model_using_the_performance_record,
        ["sample-002", "other-001"],
        "Shipped 12 Flutter applications."
      )
      report, status = check(dir, model)
      refute status.success?
      assert(
        report["errors"].any? { |e| e.include?("unsupported number") },
        report["errors"].inspect
      )
    end
  end

  def test_composition_cannot_launder_an_ineligible_source
    with_workspace do |dir|
      # other-002 is eligible; a missing id is not. Every source must resolve.
      model = composed_summary(
        model_using_the_performance_record,
        ["other-002", "sample-999"],
        "Built localized settings and other Flutter screens."
      )
      report, status = check(dir, model)
      refute status.success?
      assert(
        report["errors"].any? { |e| e.include?("missing source sample-999") },
        report["errors"].inspect
      )
    end
  end

  def test_source_ref_and_source_refs_are_mutually_exclusive
    with_workspace do |dir|
      model = model_using_the_performance_record
      model["summary"] = [{
        "text" => "Built checkout flows.",
        "source_ref" => "sample-002",
        "source_refs" => ["sample-002", "other-001"]
      }]
      report, status = check(dir, model)
      refute status.success?
      assert(
        report["errors"].any? { |e| e.include?("not both") },
        report["errors"].inspect
      )
    end
  end

  def test_a_single_element_composition_is_rejected
    with_workspace do |dir|
      model = composed_summary(
        model_using_the_performance_record, ["sample-002"], "Built checkout flows."
      )
      report, status = check(dir, model)
      refute status.success?
      assert(
        report["errors"].any? { |e| e.include?("at least two source IDs") },
        report["errors"].inspect
      )
    end
  end

  def test_a_composed_item_still_counts_toward_coverage
    with_workspace do |dir|
      model = base_model
      model["summary"] = [{
        "text" => "Ran a Flutter rendering and memory optimization pass alongside checkout work.",
        "source_refs" => ["sample-001", "sample-002"]
      }]
      model["alignment"]["requirements"][0]["evidence_refs"] = ["sample-001"]
      report, status = check(dir, model)
      assert status.success?, "errors: #{report['errors']}"
      assert_equal "demonstrated", report.dig("coverage", "requirements", 0, "coverage"),
                   "a project record cited through source_refs demonstrates its requirement"
    end
  end

  def test_a_non_primary_project_record_in_source_refs_counts_toward_coverage
    with_workspace do |dir|
      model = base_model
      model["summary"] = [{
        "text" => "Built checkout work alongside a Flutter rendering and memory optimization pass.",
        "source_refs" => ["sample-002", "sample-001"]
      }]
      model["alignment"]["requirements"][0]["evidence_refs"] = ["sample-001"]
      report, status = check(dir, model)
      assert status.success?, "errors: #{report['errors']}"
      assert_equal "demonstrated", report.dig("coverage", "requirements", 0, "coverage"),
                   "every project record in source_refs must count, not only the first"
    end
  end

  # --- Interview stories in the index ---------------------------------------

  INTERVIEW_MD = <<~MD
    # sample — Interview Preparation Guide

    ## Story 1 — Removing a blocking probe from every request
    ### Feature context
    Some context.
    ### Likely follow-up questions
    1. Why cache it?

    <!-- src: sample-001 -->

    ## Story 2: Building checkout
    <!-- src: sample-002 -->

    ## Supporting fact bank
    <!-- src: other-001 -->

    ### System context (team-built, describe don't claim)
    <!-- src: other-002 -->
  MD

  def with_interview_workspace
    with_workspace do |dir|
      FileUtils.mkdir_p(File.join(dir, "artifacts", "interview"))
      File.write(File.join(dir, "artifacts", "interview", "sample.md"), INTERVIEW_MD)
      _out, err, status = Open3.capture3("python3", INDEXER, "--root", dir)
      raise "indexer failed: #{err}" unless status.success?
      yield dir, YAML.safe_load(File.read(File.join(dir, "index", "evidence-index.yaml")))
    end
  end

  def test_both_story_heading_layouts_are_recognised
    with_interview_workspace do |_dir, index|
      rows = index["records"].to_h { |r| [r["id"], r] }
      assert_equal "Removing a blocking probe from every request", rows["sample-001"]["story"],
                   "a level-2 heading with trailing markers must bind"
      assert_equal "Building checkout", rows["sample-002"]["story"],
                   "a level-3 heading with inline markers must bind"
      assert_includes rows["sample-001"]["signals"], "interview-story"
    end
  end

  def test_a_fact_bank_heading_does_not_become_a_story
    with_interview_workspace do |_dir, index|
      rows = index["records"].to_h { |r| [r["id"], r] }
      assert_nil rows["other-001"]["story"],
                 "Supporting fact bank carries no story number and must not label records"
    end
  end

  def test_system_context_records_get_no_story
    with_interview_workspace do |_dir, index|
      rows = index["records"].to_h { |r| [r["id"], r] }
      assert_nil rows["other-002"]["story"],
                 "system-context work may be described but not claimed, so it gets no story label"
    end
  end

  def test_the_story_signal_does_not_change_strength
    with_interview_workspace do |dir, index|
      with_story = index["records"].find { |r| r["id"] == "sample-001" }["strength"]
      FileUtils.rm_rf(File.join(dir, "artifacts"))
      _out, _err, _st = Open3.capture3("python3", INDEXER, "--root", dir)
      plain = YAML.safe_load(File.read(File.join(dir, "index", "evidence-index.yaml")))
      without = plain["records"].find { |r| r["id"] == "sample-001" }["strength"]
      assert_equal without, with_story,
                   "defensibility is a signal, not a score; it must not outrank measured evidence"
    end
  end

  # --- Profile sources in the index and shortlist ----------------------------
  #
  # A requirement answerable only by a confirmed responsibility used to show as
  # "no eligible evidence" in the shortlist, which reads as a portfolio gap
  # rather than the indexing gap it was.

  def test_profile_responsibilities_and_skill_groups_are_indexed
    with_workspace do |dir|
      index = YAML.safe_load(File.read(File.join(dir, "index", "evidence-index.yaml")))
      sources = index["profile_sources"]
      refute_nil sources
      ids = sources.map { |entry| entry["ref"] || entry["id"] }
      assert_includes ids, "profile-skill-001"
      group = sources.find { |entry| (entry["id"] || entry["ref"]) == "profile-skill-001" }
      assert_equal "skill-group", group["origin"]
      assert_includes group["covers"], "Performance and memory optimization"
    end
  end

  def test_profile_sources_stay_out_of_the_record_rows
    with_workspace do |dir|
      index = YAML.safe_load(File.read(File.join(dir, "index", "evidence-index.yaml")))
      record_ids = index["records"].map { |r| r["id"] }
      refute_includes record_ids, "profile-skill-001",
                      "a profile entry states a capability and cannot be strength-scored " \
                      "alongside records that demonstrate one"
    end
  end

  # --- Spelled-out quantities ------------------------------------------------
  #
  # numeric_tokens only ever matched digits, so a resume could say "three
  # clients adopted the service" while its cited record said two and every gate
  # passed. That happened to a real committed resume on 2026-07-29.

  def test_a_spelled_number_absent_from_the_source_is_rejected
    with_workspace do |dir|
      model = base_model
      model["experience"][0]["bullets"][0]["text"] =
        "Built a checkout flow with server-confirmed payment status for seven clients."
      report, status = check(dir, model)
      refute status.success?
      assert(
        report["errors"].any? { |e| e.include?("unsupported spelled number") && e.include?("seven") },
        report["errors"].inspect
      )
    end
  end

  def test_the_article_sense_of_one_is_not_treated_as_a_count
    with_workspace do |dir|
      model = base_model
      model["experience"][0]["bullets"][0]["text"] =
        "Built a checkout flow with server-confirmed payment status in one call."
      report, _status = check(dir, model)
      refute(
        report["errors"].any? { |e| e.include?("spelled number") },
        "\"one\" is overwhelmingly an article and must not be checked: #{report['errors']}"
      )
    end
  end

  # --- Competing drafts ------------------------------------------------------
  #
  # A single draft with no rival is unfalsifiable: nothing establishes it was the
  # best resume the evidence could support, only that it passed every gate.

  COMPARE = File.join(ROOT, "scripts", "ekb_compare.py")

  def compare(dir, models)
    paths = models.map do |name, model|
      path = File.join(dir, "#{name}.json")
      File.write(path, JSON.pretty_generate(model))
      "#{name}:#{path}"
    end
    stdout, stderr, status = Open3.capture3(
      "python3", COMPARE, "--models", *paths,
      "--profile", File.join(dir, "profile", "profile.yaml"),
      "--projects", File.join(dir, "projects"),
      "--json"
    )
    raise "compare produced no output: #{stderr}" if stdout.strip.empty?
    [JSON.parse(stdout), status]
  end

  def test_the_draft_demonstrating_more_wins
    with_workspace do |dir|
      weak = base_model                                  # performance only stated
      strong = model_using_the_performance_record        # performance demonstrated
      report, status = compare(dir, [["weak", weak], ["strong", strong]])
      assert status.success?, report.inspect
      assert_equal "strong", report["winner"]
      assert_operator report["drafts"]["strong"]["demonstrated"],
                      :>, report["drafts"]["weak"]["demonstrated"]
    end
  end

  def test_identical_drafts_produce_identical_numbers
    with_workspace do |dir|
      m = model_using_the_performance_record
      report, status = compare(dir, [["a", m], ["b", Marshal.load(Marshal.dump(m))]])
      assert status.success?
      # The fixture workspace has no rubric, so `score` is nil for both. What
      # must match is everything derived from the model itself.
      a = report["drafts"]["a"]
      b = report["drafts"]["b"]
      assert_equal a, b, "identical models must produce identical summaries"
      assert_equal 1, a["demonstrated"]
    end
  end

  def test_a_single_draft_cannot_be_compared
    with_workspace do |dir|
      path = File.join(dir, "only.json")
      File.write(path, JSON.pretty_generate(base_model))
      _out, stderr, status = Open3.capture3(
        "python3", COMPARE, "--models", path,
        "--profile", File.join(dir, "profile", "profile.yaml"),
        "--projects", File.join(dir, "projects")
      )
      refute status.success?
      assert_includes stderr, "at least two models"
    end
  end

  def test_an_invalid_draft_loses_to_a_valid_one
    with_workspace do |dir|
      broken = model_using_the_performance_record
      broken["experience"][0]["bullets"][0]["source_ref"] = "does-not-exist-001"
      report, _status = compare(dir, [["broken", broken],
                                      ["sound", model_using_the_performance_record]])
      assert_equal "sound", report["winner"],
                   "a draft that fails source checking must never win"
      refute report["drafts"]["broken"]["valid"]
    end
  end
end
