#!/usr/bin/env ruby

require "fileutils"
require "date"
require "json"
require "minitest/autorun"
require "open3"
require "tmpdir"
require "yaml"

class ResumeModuleTest < Minitest::Test
  ROOT = File.expand_path("..", __dir__)
  FIXTURES = File.join(__dir__, "fixtures")
  TOOL = File.join(ROOT, "scripts", "resume_render.py")
  PROFILE = File.join(FIXTURES, "profile.yaml")
  PROJECTS = File.join(FIXTURES, "projects")
  POLICY = File.join(ROOT, "config", "resume-policy.json")
  RANKING = File.join(FIXTURES, "project-ranking.yaml")

  def run_tool(*arguments)
    env = {"EKB_PYTHON" => ENV.fetch("EKB_PYTHON", "python3")}
    Open3.capture3(env, ENV.fetch("EKB_PYTHON", "python3"), TOOL, *arguments)
  end

  def with_model
    Dir.mktmpdir("ekb-resume-test-") do |directory|
      model = JSON.parse(File.read(File.join(FIXTURES, "resume.json")))
      path = File.join(directory, "resume.json")
      yield model, path, directory
    end
  end

  def write_model(path, model)
    File.write(path, JSON.pretty_generate(model) + "\n")
  end

  def validate(model, path)
    write_model(path, model)
    run_tool("validate", "--model", path, "--profile", PROFILE, "--projects", PROJECTS)
  end

  def render_model(model, directory, *extra)
    path = File.join(directory, "resume.json")
    write_model(path, model)
    output = File.join(directory, "output")
    stdout, stderr, status = run_tool(
      "render", "--model", path, "--profile", PROFILE, "--projects", PROJECTS,
      "--policy", POLICY, "--output-dir", output, *extra
    )
    [output, stdout, stderr, status]
  end

  def summary_text(word_count, sentences: 4)
    lead = %w[Software Engineer with 3+ years of experience.]
    tail_count = sentences - 1
    raise ArgumentError, "summary needs a lead and at least two words per remaining sentence" \
      if tail_count < 1 || word_count < lead.length + tail_count * 2

    remaining = word_count - lead.length
    words = Array.new(remaining - 1, "Ruby") + ["PostgreSQL"]
    base, remainder = remaining.divmod(tail_count)
    cursor = 0
    tail = Array.new(tail_count) do |index|
      size = base + (index < remainder ? 1 : 0)
      sentence = words.slice(cursor, size).join(" ") + "."
      cursor += size
      sentence
    end
    ([lead.join(" ")] + tail).join(" ")
  end

  # Office Open XML is UTF-8. Reading it with the shell's default external
  # encoding raises on any non-ASCII byte, which a real resume routinely has.
  def docx_runs(path)
    Dir.mktmpdir("ekb-docx-") do |directory|
      system("unzip", "-qq", "-o", path, "word/document.xml", "-d", directory, out: File::NULL)
      File.read(File.join(directory, "word", "document.xml"), encoding: "UTF-8")
    end
  end

  def docx_part(path, part)
    Dir.mktmpdir("ekb-docx-part-") do |directory|
      system("unzip", "-qq", "-o", path, part, "-d", directory, out: File::NULL)
      File.read(File.join(directory, part), encoding: "UTF-8")
    end
  end

  def test_valid_evidence_model
    with_model do |model, path, _directory|
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_requires_confirmed_professional_title
    with_model do |model, path, _directory|
      model["basics"].delete("title")
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "name, title, contact, links, and mobility"
    end

    with_model do |model, path, _directory|
      model["basics"]["title"] = {
        "text" => "Software Engineer",
        "source_ref" => "profile-experience-001"
      }
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "must cite profile.professional_title profile-title-001"
    end
  end

  def test_allows_freelance_projects_to_be_omitted
    with_model do |model, path, _directory|
      model["projects"] = []
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_rejects_a_repeated_freelance_project
    with_model do |model, path, _directory|
      model["projects"] << Marshal.load(Marshal.dump(model["projects"][0]))
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "Freelance Projects repeats a curated project"
    end
  end

  def test_rejects_forbidden_em_dash_in_public_text
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] =
        "Contributed to a data import pipeline with Ruby — and PostgreSQL."
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "forbidden em dash symbol"
    end
  end

  def test_rejects_forbidden_ai_style_wording
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] =
        "Seamlessly contributed to a data import pipeline with Ruby and PostgreSQL."
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "forbidden AI-style wording"
      assert_includes stderr, "seamlessly"
    end
  end

  def test_rejects_forbidden_ai_style_summary_phrase
    with_model do |model, path, _directory|
      model["summary"][0]["text"] = model["summary"][0]["text"].sub(
        "contributing to", "highly skilled in"
      )
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "forbidden AI-style wording"
      assert_includes stderr, "highly skilled"
    end
  end

  def test_rejects_an_overlong_achievement_bullet
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] =
        ((["word"] * 29).join(" ") + ".")
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "contains 29 words; maximum is 28"
    end
  end

  def test_rejects_multiple_achievements_in_one_bullet
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] =
        "Contributed to a data import pipeline. Added PostgreSQL persistence."
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "contains 2 sentences; maximum is 1"
    end
  end

  def test_rejects_a_vague_duty_opening
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] =
        "Worked on a data import pipeline with Ruby and PostgreSQL."
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "starts with vague duty wording"
      assert_includes stderr, "worked on"
    end
  end

  def test_rejects_gameable_test_case_and_file_counts
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] =
        "Grew the unit-test suite from 61 to 84 cases across 18 files."
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "gameable testing-size count"
      assert_includes stderr, "describe tested behaviors"
    end
  end

  def test_rejects_gameable_source_code_line_and_file_counts
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] =
        "Decomposed a cart controller from 946 to 177 lines across a 48-file change."
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "gameable code-size count"
      assert_includes stderr, "describe the structural change"
    end
  end

  def test_accepts_testing_scope_described_by_behavior
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] =
        "Tested import validation, rollback, timeout, and malformed-response paths."
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_rejects_unknown_resume_mode
    with_model do |model, path, _directory|
      model["target"]["mode"] = "general"
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "target.mode must be master or job-targeted"
    end
  end

  def test_job_targeted_resume_requires_a_summary_lead
    with_model do |model, path, _directory|
      model["target"].delete("summary_lead")
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "require target.summary_lead"
    end
  end

  def test_job_targeted_summary_must_begin_with_declared_lead
    with_model do |model, path, _directory|
      model["target"]["summary_lead"] = "Software Engineer specializing in Flutter"
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "must begin with target.summary_lead"
    end
  end

  def test_job_targeted_summary_lead_must_preserve_confirmed_profile_title
    with_model do |model, path, _directory|
      model["target"]["summary_lead"] = "Ruby Engineer"
      model["summary"][0]["text"] = model["summary"][0]["text"].sub(
        "Software Engineer", "Ruby Engineer"
      )
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "must begin with the confirmed basics.title"
    end
  end

  def test_outside_country_resume_requires_mobility_line
    with_model do |model, path, _directory|
      model["target"]["job_country"] = "Germany"
      model["target"]["job_country_code"] = "DE"
      model["target"]["location_scope"] = "outside-country"
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "basics.mobility is required"
    end
  end

  def test_master_resume_requires_mobility_line
    with_model do |model, path, _directory|
      model["target"]["mode"] = "master"
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "basics.mobility is required"
    end
  end

  def test_outside_country_resume_accepts_confirmed_relocation_line
    with_model do |model, path, _directory|
      model["target"]["job_country"] = "Germany"
      model["target"]["job_country_code"] = "DE"
      model["target"]["location_scope"] = "outside-country"
      model["basics"]["mobility"] = {
        "text" => "Open to relocation.",
        "source_ref" => "profile-eligibility-003"
      }
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_mobility_line_rejects_non_relocation_eligibility_source
    with_model do |model, path, _directory|
      model["basics"]["mobility"] = {
        "text" => "Authorized to work in Testland.",
        "source_ref" => "profile-eligibility-002"
      }
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "type relocation"
    end
  end

  def test_location_scope_must_match_confirmed_countries
    with_model do |model, path, _directory|
      model["target"]["job_country"] = "Germany"
      model["target"]["job_country_code"] = "DE"
      model["target"]["location_scope"] = "same-country"
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "target.location_scope must be \"outside-country\""
    end
  end

  def test_requires_a_reason_when_a_supported_required_job_requirement_is_omitted
    with_model do |model, path, _directory|
      model["alignment"]["requirements"][0] = {
        "term" => "Batch processing",
        "aliases" => ["Batch processing"],
        "priority" => "required",
        "critical" => false,
        "status" => "supported_not_selected",
        "evidence_refs" => ["fixture-quantified-001"]
      }
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "needs selection_reason"
    end
  end

  def test_accepts_a_reasoned_supported_required_job_requirement_omission
    with_model do |model, path, _directory|
      model["alignment"]["requirements"][0] = {
        "term" => "Batch processing",
        "aliases" => ["Batch processing"],
        "priority" => "required",
        "critical" => false,
        "status" => "supported_not_selected",
        "evidence_refs" => ["fixture-quantified-001"],
        "selection_reason" => "Omitted to keep the one-page draft focused on the target's critical API work."
      }
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_rejects_inferred_source
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0] = {
        "text" => "The pipeline likely shortened customer onboarding.",
        "source_ref" => "fixture-inferred-001"
      }
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "ineligible kind"
    end
  end

  def test_rejects_team_context_as_personal_claim
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0] = {
        "text" => "Contributed to the product billing subsystem.",
        "source_ref" => "fixture-team-001"
      }
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "team-context"
    end
  end

  def test_rejects_unsupported_number
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] = "Contributed to a data import pipeline supporting 99 formats."
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "unsupported number"
    end
  end

  def test_rejects_profile_text_that_does_not_match_confirmed_values
    with_model do |model, path, _directory|
      model["experience"][0]["title"]["text"] = "Principal Software Engineer"
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "not supported by confirmed profile values"
    end
  end

  def test_rejects_leadership_for_contributed_source
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] = "Led a data import pipeline supporting 3 formats with Ruby and PostgreSQL."
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "overstates contributed"
    end
  end

  def test_rejects_direct_implementation_wording_for_contributed_source
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] =
        "Built a data import pipeline supporting 3 formats with Ruby and PostgreSQL."
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "overstates contributed"
    end
  end

  def test_rejects_independent_ownership_without_explicit_source_support
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0] = {
        "text" => "Independently implemented a scheduling service with Ruby and PostgreSQL.",
        "source_ref" => "stronger-001"
      }
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "independent-ownership wording without explicit source support"
    end
  end

  def test_accepts_legacy_shared_as_contributed
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0] = {
        "text" => "Contributed to a background job integration using Redis.",
        "source_ref" => "fixture-legacy-shared-001"
      }
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_renders_docx_pdf_and_validation
    with_model do |model, path, directory|
      write_model(path, model)
      output = File.join(directory, "output")
      stdout, stderr, status = run_tool(
        "render",
        "--model", path,
        "--profile", PROFILE,
        "--projects", PROJECTS,
        "--policy", POLICY,
        "--output-dir", output
      )
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
      %w[
        resume.docx
        resume.pdf
        Casey_Engineer_Software_Engineer_CV.docx
        Casey_Engineer_Software_Engineer_CV.pdf
        validation.json
        validation.md
      ].each do |name|
        path = File.join(output, name)
        assert File.file?(path), "missing #{name}"
        assert_operator File.size(path), :>, 100
      end
      document = docx_runs(File.join(output, "resume.docx"))
      assert_operator document.index("Casey Engineer"), :<, document.index("Software Engineer")
      assert_operator document.index("Software Engineer"), :<, document.index("Email")
      refute File.exist?(File.join(output, "resume.txt"))
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert report["valid"]
      assert_equal "job-targeted", report["resume_mode"]
      assert_equal 0, report.dig("document_validation", "docx_structure", "tables")
      assert_equal 0, report.dig("document_validation", "docx_structure", "inline_shapes")
      assert_operator report.dig("document_validation", "pdf_pages"), :>=, 1
      fill_ratios = report.dig("document_validation", "content_fill_ratios")
      assert_equal report.dig("document_validation", "pdf_pages"), fill_ratios.length
      assert fill_ratios.all? { |ratio| ratio.between?(0.0, 1.0) }
      assert_equal report.dig("document_validation", "pdf_pages"),
                   report.dig("document_validation", "orphaned_wraps").length
      assert_equal 20.0, report.dig("presentation", "bullet_layout", "text_indent_pt")
      assert_equal 11.0, report.dig("presentation", "bullet_layout", "hanging_pt")
      assert_equal(-1.5, report.dig("presentation", "bullet_layout", "marker_vertical_offset_pt"))
      assert_equal "Casey_Engineer_Software_Engineer_CV",
                   report.dig("presentation", "attachment_stem")
      refute report.dig("document_validation", "pdf_password_protected")
      assert_includes report.dig("document_validation", "warnings").join(" "),
                      "no phone number"
      refute_includes report.dig("document_validation", "warnings").join(" "),
                      "no confirmed professional profile link"
      assert_includes report.dig("document_validation", "warnings").join(" "),
                      "no CEFR level"
    end
  end

  def test_docx_bullets_use_indented_text_and_a_lowered_real_marker
    with_model do |model, _path, directory|
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      document = docx_part(File.join(output, "resume.docx"), "word/document.xml")
      numbering = docx_part(File.join(output, "resume.docx"), "word/numbering.xml")
      assert_match(%r{<w:ind w:left="400" w:hanging="220"/>}, document)
      assert_match(
        %r{<w:pStyle w:val="ListBullet"/>.*?<w:position w:val="-3"/>}m,
        numbering
      )
      assert_match(%r{<w:lvlText w:val="•"/>}, numbering)
      assert_match(%r{<w:rFonts w:ascii="Arial" w:hAnsi="Arial"}, numbering)
    end
  end

  def test_one_page_resume_has_no_continuation_header
    with_model do |model, _path, directory|
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert_empty report.dig("document_validation", "docx_structure", "header_footer_text")
    end
  end

  def test_renderers_expose_readable_entry_spacing_tokens
    with_model do |model, _path, directory|
      model["experience"] << Marshal.load(Marshal.dump(model["experience"].first))
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      spacing = report.dig("presentation", "spacing_pt")
      assert_equal 8, spacing["experience_entry_before"]
      assert_equal 4, spacing["entry_meta_after"]
      assert_equal 5, spacing["project_entry_before"]
      assert_operator spacing["section_before"], :>, spacing["paragraph_after"]
      document = docx_part(File.join(output, "resume.docx"), "word/document.xml")
      assert_match(%r{<w:spacing w:after="80"/>}, document)
      assert_match(%r{<w:spacing w:before="160" w:after="20"/>}, document)
    end
  end

  def test_career_breaks_are_optional_and_compete_with_experience
    policy = JSON.parse(File.read(POLICY, encoding: "UTF-8"))
    assert_equal "omit", policy.dig("career_breaks", "default")
    assert_equal true, policy.dig("career_breaks", "competes_for_page_space")
  end

  def test_engagement_policy_requires_a_distinct_incremental_signal
    policy = JSON.parse(File.read(POLICY, encoding: "UTF-8"))
    rule = policy.dig("job_targeted_content_balance", "engagement_marginal_value")
    assert_includes rule, "Remove it when its only incremental value"
    assert_includes rule, "Prefer a stronger second bullet"
  end

  def test_employer_project_is_rejected_from_freelance_projects
    with_model do |model, path, _directory|
      model["projects"] = [{
        "primary" => {"text" => "Data Importer", "source_ref" => "fixture-001"},
        "secondary" => nil,
        "date" => nil,
        "details" => [{
          "text" => "Contributed to a data import pipeline supporting 3 formats.",
          "source_ref" => "fixture-001"
        }]
      }]
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "Freelance Projects includes employer project fixture"
    end
  end

  def test_independent_project_is_rejected_from_experience
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0] = {
        "text" => "Implemented a CSV export utility with Ruby.",
        "source_ref" => "lowest-001"
      }
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "places independent project lowest under Experience"
    end
  end

  def test_ai_skill_without_work_example_is_warned
    with_model do |model, _path, directory|
      model["skills"] << {
        "name" => "AI tools",
        "items" => [{"text" => "Codex", "source_ref" => "profile-skill-ai-001"}]
      }
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      warnings = JSON.parse(File.read(File.join(output, "validation.json")))
        .dig("document_validation", "warnings").join(" ")
      assert_includes warnings, "AI tools appear in Skills but not"
    end
  end

  def test_ai_skill_with_supported_work_example_is_not_warned
    with_model do |model, _path, directory|
      model["skills"] << {
        "name" => "AI tools",
        "items" => [{"text" => "Codex", "source_ref" => "profile-skill-ai-001"}]
      }
      model["experience"][0]["bullets"] << {
        "text" => "Used Codex to investigate import failures and prepare a verified repair.",
        "source_ref" => "fixture-ai-001"
      }
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      warnings = JSON.parse(File.read(File.join(output, "validation.json")))
        .dig("document_validation", "warnings").join(" ")
      refute_includes warnings, "AI tools appear in Skills but not"
    end
  end

  def test_certificates_render_name_issuer_and_date_under_new_heading
    with_model do |model, path, directory|
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["certifications"] = [{
        "id" => "profile-certification-001",
        "name" => "Example Engineering Certificate",
        "issuer" => "Example Institute",
        "issued" => "2025-03",
        "url" => "https://certs.example.test/verify",
        "kind" => "user-stated"
      }]
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      model["certifications"] = [{
        "primary" => {
          "text" => "Example Engineering Certificate",
          "source_ref" => "profile-certification-001",
          "url" => "https://certs.example.test/verify"
        },
        "secondary" => {"text" => "Example Institute", "source_ref" => "profile-certification-001"},
        "date" => {"text" => "Mar 2025", "source_ref" => "profile-certification-001"},
        "details" => []
      }]
      write_model(path, model)
      output = File.join(directory, "output")
      _stdout, stderr, status = run_tool(
        "render", "--model", path, "--profile", profile_path, "--projects", PROJECTS,
        "--policy", POLICY, "--output-dir", output
      )
      assert status.success?, stderr
      runs = docx_runs(File.join(output, "resume.docx"))
      assert_includes runs, "CERTIFICATES"
      refute_includes runs, "CERTIFICATIONS"
      assert_includes runs, "Example Engineering Certificate"
      assert_includes runs, "Example Institute"
      assert_includes runs, "Mar 2025"
    end
  end

  def test_warns_when_a_single_page_resume_is_underfilled
    with_model do |model, _path, directory|
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert_equal 1, report.dig("document_validation", "pdf_pages")
      assert_operator report.dig("document_validation", "content_fill_ratios", 0), :<, 0.84
      assert_includes report.dig("document_validation", "warnings").join(" "), "underfilled"
    end
  end

  def test_european_resume_renders_a4_and_optional_sections
    Dir.mktmpdir("ekb-resume-market-test-") do |directory|
      model = File.join(directory, "resume.json")
      FileUtils.cp(File.join(FIXTURES, "resume.json"), model)
      output = File.join(directory, "output")
      stdout, stderr, status = run_tool(
        "render",
        "--model", model,
        "--profile", PROFILE,
        "--projects", PROJECTS,
        "--policy", POLICY,
        "--output-dir", output
      )
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert report["valid"]
      assert_equal 1, report["policy_version"]
      assert_equal "A4", report.dig("document_validation", "page_size")
      assert_equal [], report.dig("document_validation", "errors")
      assert_operator report.dig("document_validation", "pdf_pages"), :<=, 2
    end
  end

  def test_north_american_resume_uses_letter_and_accepts_120_word_override
    with_model do |model, path, directory|
      model["target"]["market"] = "north-america"
      model["target"]["market_basis"] = "user-override"
      model["layout"]["summary_word_limit"] = 120
      model["summary"][0]["text"] = summary_text(120)
      write_model(path, model)
      output = File.join(directory, "output")
      _stdout, stderr, status = run_tool(
        "render", "--model", path, "--profile", PROFILE, "--projects", PROJECTS,
        "--policy", POLICY, "--output-dir", output
      )
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert_equal "LETTER", report.dig("document_validation", "page_size")
    end
  end

  def test_summary_defaults_to_ninety_words_and_accepts_four_sentences_in_every_market
    with_model do |model, path, _directory|
      model["summary"][0]["text"] = summary_text(90)
      _stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
    end
  end

  def test_summary_requires_years_of_experience
    with_model do |model, path, _directory|
      model["summary"][0]["text"] = model["summary"][0]["text"].sub(
        " with 3+ years of experience", ""
      )
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "exactly one N+ years of experience figure"
    end
  end

  def test_summary_rejects_years_that_exceed_the_confirmed_timeline
    with_model do |model, path, _directory|
      model["summary"][0]["text"] = model["summary"][0]["text"].sub("3+ years", "4+ years")
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "confirmed non-overlapping profile timeline supports 3+"
    end
  end

  def test_summary_rejects_more_than_ninety_words
    with_model do |model, path, _directory|
      model["summary"][0]["text"] = summary_text(91)
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "90-word"
    end
  end

  def test_summary_honors_an_explicit_shorter_override
    with_model do |model, path, _directory|
      model["layout"]["summary_word_limit"] = 60
      model["summary"][0]["text"] = summary_text(61)
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "60-word"
    end
  end

  def test_summary_accepts_an_explicit_longer_override
    with_model do |model, path, _directory|
      model["layout"]["summary_word_limit"] = 120
      model["summary"][0]["text"] = summary_text(120)
      _stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
    end
  end

  def test_summary_rejects_fewer_than_three_sentences
    with_model do |model, path, _directory|
      model["summary"][0]["text"] = summary_text(45, sentences: 2)
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "3 to 5 complete sentences; found 2"
    end
  end

  def test_summary_rejects_more_than_five_sentences
    with_model do |model, path, _directory|
      model["summary"][0]["text"] = summary_text(70, sentences: 6)
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "3 to 5 complete sentences; found 6"
    end
  end

  def test_renders_freelance_projects
    with_model do |model, _path, directory|
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert report["valid"]
      assert_equal 0, report.dig("document_validation", "errors").length
      assert_equal ["lowest"], report.dig(
        "source_validation", "project_selection", "named_in_freelance_projects"
      )
      validation_text = File.read(File.join(output, "validation.md"))
      assert_includes validation_text, "Project evidence used anywhere: fixture, lowest"
      assert_includes validation_text, "Named in Freelance Projects: lowest"
    end
  end

  def test_rejects_a_partial_number_match
    Dir.mktmpdir("ekb-resume-number-test-") do |directory|
      model = JSON.parse(File.read(File.join(FIXTURES, "resume.json")))
      model["experience"][0]["bullets"][0]["text"] = "Contributed to a data import pipeline supporting 4 formats with Ruby and PostgreSQL."
      path = File.join(directory, "resume.json")
      write_model(path, model)
      stdout, _stderr, status = run_tool("validate", "--model", path, "--profile", PROFILE, "--projects", PROJECTS)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "unsupported number"
    end
  end

  def test_accepts_exact_abbreviated_scale_and_unit
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0] = {
        "text" => "Processed 1K+ users in 2 hours through a verified import workflow.",
        "source_ref" => "fixture-quantified-001"
      }
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_rejects_spelled_out_quantities_in_resume_prose
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["text"] =
        "Contributed to a data import pipeline supporting three formats."
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "uses spelled-out quantity 'three'"
      assert_includes stderr, "use digits by default"
    end
  end

  def test_accepts_digits_when_the_source_spells_out_the_same_quantity
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0] = {
        "text" => "Processed imports for 2 clients through a verified workflow.",
        "source_ref" => "fixture-word-number-001"
      }
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_rejects_matched_keyword_without_selected_evidence
    Dir.mktmpdir("ekb-resume-keyword-test-") do |directory|
      model = JSON.parse(File.read(File.join(FIXTURES, "resume.json")))
      model["alignment"]["requirements"][0]["evidence_refs"] = ["fixture-legacy-shared-001"]
      path = File.join(directory, "resume.json")
      write_model(path, model)
      stdout, _stderr, status = run_tool("validate", "--model", path, "--profile", PROFILE, "--projects", PROJECTS)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "no evidence source selected"
    end
  end

  def test_rejects_ineligible_keyword_evidence
    with_model do |model, path, _directory|
      model["alignment"]["requirements"] << {
        "term" => "Customer onboarding", "aliases" => ["customer onboarding"],
        "priority" => "preferred", "critical" => false,
        "status" => "supported_not_selected", "evidence_refs" => ["fixture-inferred-001"]
      }
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "ineligible kind"
    end
  end

  def test_profile_timeline_gap_is_a_warning_not_a_blocker
    with_model do |model, path, directory|
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["experience"] << {
        "id" => "profile-experience-002", "organization" => "Earlier Systems",
        "title" => "Developer", "start" => "2020-01", "end" => "2021-01",
        "employment_type" => "full-time", "projects" => [], "kind" => "user-stated"
      }
      model["summary"][0]["text"] = model["summary"][0]["text"].sub("3+ years", "4+ years")
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      write_model(path, model)
      stdout, stderr, status = run_tool("validate", "--model", path, "--profile", profile_path, "--projects", PROJECTS)
      assert status.success?, stderr
      assert_includes JSON.parse(stdout)["warnings"].join(" "), "unexplained gap"
    end
  end

  def test_confirmed_career_break_explains_profile_gap
    with_model do |model, path, directory|
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["experience"] << {
        "id" => "profile-experience-002", "organization" => "Earlier Systems",
        "title" => "Developer", "start" => "2020-01", "end" => "2021-01",
        "employment_type" => "full-time", "projects" => [], "kind" => "user-stated"
      }
      model["summary"][0]["text"] = model["summary"][0]["text"].sub("3+ years", "4+ years")
      profile["career_breaks"] = [{
        "id" => "profile-career-break-001", "label" => "Career break",
        "start" => "2021-02", "end" => "2021-12", "details" => [], "kind" => "user-stated"
      }]
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      write_model(path, model)
      stdout, stderr, status = run_tool("validate", "--model", path, "--profile", profile_path, "--projects", PROJECTS)
      assert status.success?, stderr
      refute_includes JSON.parse(stdout)["warnings"].join(" "), "unexplained gap"
    end
  end

  def test_year_only_career_break_covers_the_stated_end_year
    with_model do |model, path, directory|
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["experience"] << {
        "id" => "profile-experience-002", "organization" => "Earlier Systems",
        "title" => "Developer", "start" => "2020-01", "end" => "2020-12",
        "employment_type" => "full-time", "projects" => [], "kind" => "user-stated"
      }
      model["summary"][0]["text"] = model["summary"][0]["text"].sub("3+ years", "4+ years")
      profile["career_breaks"] = [{
        "id" => "profile-career-break-001", "label" => "Confirmed service",
        "start" => 2021, "end" => 2021, "precision" => "year",
        "details" => [], "kind" => "user-stated"
      }]
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      write_model(path, model)
      stdout, stderr, status = run_tool(
        "validate", "--model", path, "--profile", profile_path, "--projects", PROJECTS
      )
      assert status.success?, stderr
      refute_includes JSON.parse(stdout)["warnings"].join(" "), "unexplained gap"
    end
  end

  def test_experience_years_count_overlapping_roles_once
    with_model do |model, path, directory|
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["experience"] << {
        "id" => "profile-experience-002", "organization" => "Overlapping Systems",
        "title" => "Consultant", "start" => "2023-01", "end" => "2024-12",
        "employment_type" => "part-time", "projects" => [], "kind" => "user-stated"
      }
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      write_model(path, model)
      stdout, stderr, status = run_tool(
        "validate", "--model", path, "--profile", profile_path, "--projects", PROJECTS
      )
      assert status.success?, "#{stderr}\n#{stdout}"
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_two_page_resume_uses_only_exact_continuation_contact
    with_model do |model, path, directory|
      bullet = model["experience"][0]["bullets"][0]
      model["experience"][0]["bullets"] = Array.new(4) { bullet.dup }
      model["experience"] = Array.new(8) { model["experience"][0].transform_values { |value| value.is_a?(Array) ? value.map(&:dup) : value } }
      model["layout"]["page_target"] = 2
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["preferences"]["page_target"] = 2
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      write_model(path, model)
      output = File.join(directory, "output")
      _stdout, stderr, status = run_tool(
        "render", "--model", path, "--profile", profile_path, "--projects", PROJECTS,
        "--policy", POLICY, "--output-dir", output
      )
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert_equal 2, report.dig("document_validation", "pdf_pages")
      assert_equal ["Casey Engineer | Email | Portfolio"], report.dig("document_validation", "docx_structure", "header_footer_text")
    end
  end

  # --- Enhancement 1: automatic hyperlinks ---------------------------------

  def test_rejects_page_target_that_ignores_profile_preference
    with_model do |model, path, _directory|
      model["layout"]["page_target"] = 2
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "does not match profile.preferences.page_target 1"
    end
  end

  def test_rejects_deliberate_page_break_on_one_page_target
    with_model do |model, path, _directory|
      model["layout"]["page_break_before"] = "selected-projects"
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "only valid when page_target is 2"
    end
  end

  def test_accepts_a_hyperlink_recorded_in_the_profile
    with_model do |model, path, _directory|
      model["experience"][0]["organization"]["url"] = "https://example.test/systems"
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_rejects_a_raw_address_as_visible_profile_link_text
    with_model do |model, path, _directory|
      model["basics"]["links"][0]["text"] = "example.test/casey"
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "exposes an address"
    end
  end

  def test_rejects_an_address_like_label_in_the_profile_source
    with_model do |model, path, directory|
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["links"][0]["label"] = "example.test/casey"
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      write_model(path, model)
      stdout, _stderr, status = run_tool(
        "validate", "--model", path, "--profile", profile_path, "--projects", PROJECTS
      )
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "profile source profile-link-001 has an address-like label"
    end
  end

  def test_rejects_a_profile_link_that_ignores_its_recorded_label
    with_model do |model, path, _directory|
      model["basics"]["links"][0]["text"] = "Website"
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), 'must use profile label "Portfolio"'
    end
  end

  def test_rejects_omitted_confirmed_header_hyperlinks
    with_model do |model, path, _directory|
      model["basics"]["contact"][0].delete("url")
      model["basics"]["links"][0].delete("url")
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      errors = JSON.parse(stdout)["errors"].join(" ")
      assert_includes errors, "resume.basics.contact[0] omits the confirmed profile hyperlink"
      assert_includes errors, "resume.basics.links[0] omits the confirmed profile hyperlink"
    end
  end

  def test_rejects_a_header_label_paired_with_another_profile_url
    with_model do |model, path, _directory|
      model["basics"]["links"][0]["url"] = "mailto:engineer@example.test"
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "resume.basics.links[0].url must use the URL recorded on profile-link-001"
    end
  end

  def test_accepts_a_literal_unlinked_phone_value
    with_model do |model, path, directory|
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["contact"] << {
        "id" => "profile-contact-002", "type" => "phone", "value" => "+00 000 000 0000",
        "label" => "+00 000 000 0000", "url" => nil, "kind" => "user-stated"
      }
      model["basics"]["contact"] << {
        "text" => "+00 000 000 0000", "source_ref" => "profile-contact-002"
      }
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      write_model(path, model)
      stdout, stderr, status = run_tool(
        "validate", "--model", path, "--profile", profile_path, "--projects", PROJECTS
      )
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_rejects_a_hyperlinked_phone_word
    with_model do |model, path, directory|
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["contact"] << {
        "id" => "profile-contact-002", "type" => "phone", "value" => "+00 000 000 0000",
        "label" => "Phone", "url" => "tel:+000000000000", "kind" => "user-stated"
      }
      model["basics"]["contact"] << {
        "text" => "Phone", "source_ref" => "profile-contact-002", "url" => "tel:+000000000000"
      }
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      write_model(path, model)
      stdout, _stderr, status = run_tool(
        "validate", "--model", path, "--profile", profile_path, "--projects", PROJECTS
      )
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "phone contact and must not carry a hyperlink"
    end
  end

  def test_rejects_a_hyperlink_absent_from_the_profile
    with_model do |model, path, _directory|
      model["experience"][0]["organization"]["url"] = "https://invented.test/systems"
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "not a link recorded in profile.yaml"
    end
  end

  def test_rejects_a_hyperlink_whose_status_is_not_confirmed
    with_model do |model, path, _directory|
      model["experience"][0]["organization"]["url"] = "https://code.example.test/second"
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "link_status \"unconfirmed\""
    end
  end

  def test_warns_when_a_confirmed_employer_link_is_not_used
    with_model do |model, path, _directory|
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert_includes JSON.parse(stdout)["warnings"].join(" "), "renders unlinked"
    end
  end

  def test_rejects_a_whole_bullet_hyperlink
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"][0]["url"] = "https://play.example.test/fixture"
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "would hyperlink narrative prose"
    end
  end

  def test_renders_only_link_text_inside_narrative_prose
    with_model do |model, _path, directory|
      model["projects"][0]["details"][0] = {
        "text" => "CSV Export Utility delivered a Ruby export workflow.",
        "source_ref" => "lowest-001",
        "url" => "https://code.example.test/lowest",
        "link_text" => "CSV Export Utility"
      }
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      document = docx_runs(File.join(output, "resume.docx"))
      hyperlinks = document.scan(%r{<w:hyperlink\b.*?</w:hyperlink>}m)
      partial = hyperlinks.find { |element| element.include?("CSV Export Utility") }
      refute_nil partial
      refute_includes partial, "delivered a Ruby export workflow"
    end
  end

  def test_accepts_project_backed_summary_without_a_link
    with_model do |model, path, _directory|
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
    end
  end

  def test_rejects_any_summary_hyperlink
    with_model do |model, path, _directory|
      model["summary"][0]["url"] = "https://play.example.test/fixture"
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "summary prose must render without hyperlinks"
    end
  end

  def test_unlinked_summary_project_has_no_link_warning
    with_model do |model, path, _directory|
      model["summary"] = [{
        "text" => summary_text(40),
        "source_refs" => ["stronger-001", "profile-experience-001"]
      }]
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      refute_includes JSON.parse(stdout)["warnings"].join(" "), "summary item"
    end
  end

  def test_renders_hyperlinks_into_docx_and_pdf
    with_model do |model, _path, directory|
      model["experience"][0]["organization"]["url"] = "https://example.test/systems"
      output, stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
      document = docx_runs(File.join(output, "resume.docx"))
      assert_includes document, "w:hyperlink"
      assert_includes document, '<w:color w:val="0563C1"/>'
      assert_includes document, '<w:u w:val="single"/>'
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert_equal "auto", report.dig("presentation", "hyperlinks")
      assert_equal "#0563C1", report.dig("presentation", "hyperlink_color")
      assert report.dig("presentation", "hyperlink_underline")
      assert_operator report.dig("presentation", "linked_items"), :>=, 1
      pdf = File.binread(File.join(output, "resume.pdf"))
      assert_includes pdf, "example.test/systems"
      assert_includes pdf, "code.example.test/lowest"
    end
  end

  def test_text_export_keeps_labels_without_exposing_addresses
    with_model do |model, _path, directory|
      output, _stdout, stderr, status = render_model(model, directory, "--include-text")
      assert status.success?, stderr
      text = File.read(File.join(output, "resume.txt"))
      assert_includes text, "Email | Portfolio"
      refute_includes text, "mailto:engineer@example.test"
      refute_includes text, "https://example.test/casey"
      refute_includes text, "https://code.example.test/lowest"
    end
  end

  # --- Enhancement 3: keyword highlighting --------------------------------

  def test_emphasizes_matched_requirement_terms_in_the_docx
    with_model do |model, _path, directory|
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert_equal "matched-requirements", report.dig("presentation", "emphasis")
      assert_includes report.dig("presentation", "emphasis_terms"), "Ruby"
      assert_operator report.dig("presentation", "emphasis_applied"), :>, 0
      document = docx_runs(File.join(output, "resume.docx"))
      assert_match(%r{<w:b/>(?:(?!</w:r>).)*Ruby}m, document.gsub("\n", ""))
    end
  end

  def test_unsupported_requirements_are_never_emphasized
    with_model do |model, _path, directory|
      output, _stdout, _stderr, _status = render_model(model, directory)
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      refute_includes report.dig("presentation", "emphasis_terms"), "Kubernetes"
    end
  end

  def test_emphasize_false_suppresses_a_matched_term
    with_model do |model, _path, directory|
      model["alignment"]["requirements"][0]["emphasize"] = false
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert_equal [], report.dig("presentation", "emphasis_terms")
      assert_includes report.dig("document_validation", "warnings").join(" "), "nothing is highlighted"
    end
  end

  def test_generic_product_and_ui_aliases_are_not_emphasized
    with_model do |model, _path, directory|
      model["alignment"]["requirements"][0]["aliases"].concat(
        ["app", "mobile", "screen", "widget"]
      )
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      terms = JSON.parse(File.read(File.join(output, "validation.json")))
        .dig("presentation", "emphasis_terms")
      assert_includes terms, "Ruby"
      refute_includes terms, "app"
      refute_includes terms, "mobile"
      refute_includes terms, "screen"
      refute_includes terms, "widget"
    end
  end

  def test_emphasis_is_capped_and_reports_what_it_dropped
    with_model do |model, _path, directory|
      extra = (1..15).map do |index|
        {"term" => "Term#{index}", "aliases" => ["Ruby"], "priority" => "preferred",
         "critical" => false, "status" => "matched", "evidence_refs" => ["fixture-001"]}
      end
      model["alignment"]["requirements"].concat(extra)
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert_includes report.dig("document_validation", "warnings").join(" "), "Emphasis capped at 12"
    end
  end

  # --- Optional presentation: plain export --------------------------------

  def test_ats_plain_drops_links_and_emphasis_without_changing_text
    with_model do |model, path, directory|
      model["experience"][0]["organization"]["url"] = "https://example.test/systems"
      styled, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      styled_lines = JSON.parse(File.read(File.join(styled, "validation.json")))
        .dig("document_validation", "expected_lines")

      Dir.mktmpdir("ekb-resume-plain-") do |plain_directory|
        plain, _plain_stdout, plain_stderr, plain_status =
          render_model(model, plain_directory, "--ats-plain")
        assert plain_status.success?, plain_stderr
        report = JSON.parse(File.read(File.join(plain, "validation.json")))
        assert_equal "off", report.dig("presentation", "hyperlinks")
        assert_equal "none", report.dig("presentation", "emphasis")
        assert_equal 0, report.dig("presentation", "emphasis_applied")
        assert_equal styled_lines, report.dig("document_validation", "expected_lines")
        refute_includes docx_runs(File.join(plain, "resume.docx")), "w:hyperlink"
      end
    end
  end

  # --- Enhancement 2: project ranking -------------------------------------

  def test_ranking_reports_selected_projects_with_their_ranks
    with_model do |model, path, _directory|
      write_model(path, model)
      stdout, stderr, status = run_tool(
        "validate", "--model", path, "--profile", PROFILE, "--projects", PROJECTS,
        "--ranking", RANKING
      )
      assert status.success?, stderr
      report = JSON.parse(stdout)
      assert report.dig("checks", "ranking_loaded")
      assert_equal ["fixture", "lowest"], report.dig("project_selection", "selected")
      assert_equal [2, 3], report.dig("project_selection", "ranks")
      assert_equal ["fixture", "lowest"], report.dig("project_selection", "evidence_used")
      assert_equal ["lowest"],
                   report.dig("project_selection", "named_in_freelance_projects")
    end
  end

  def test_ranking_warns_about_a_rank_inversion
    with_model do |model, path, _directory|
      write_model(path, model)
      stdout, _stderr, status = run_tool(
        "validate", "--model", path, "--profile", PROFILE, "--projects", PROJECTS,
        "--ranking", RANKING
      )
      assert status.success?
      assert_includes JSON.parse(stdout)["warnings"].join(" "), "rank inversion"
      assert_includes JSON.parse(stdout)["warnings"].join(" "), "stronger (rank 1)"
    end
  end

  def test_master_warns_when_highest_ranked_eligible_project_is_not_used
    with_model do |model, path, _directory|
      model["target"]["mode"] = "master"
      model["basics"]["mobility"] = {
        "text" => "Open to relocation.",
        "source_ref" => "profile-eligibility-003"
      }
      write_model(path, model)
      stdout, _stderr, status = run_tool(
        "validate", "--model", path, "--profile", PROFILE, "--projects", PROJECTS,
        "--ranking", RANKING
      )
      assert status.success?
      warning_text = JSON.parse(stdout)["warnings"].join(" ")
      assert_includes warning_text,
                      "master resume omits highest-ranked eligible project stronger (rank 1)"
    end
  end

  def test_selecting_the_highest_ranked_project_raises_no_inversion
    with_model do |model, path, _directory|
      model["experience"][0]["bullets"] = [{
        "text" => "Implemented a scheduling service with Ruby and PostgreSQL.",
        "source_ref" => "stronger-001"
      }]
      model["summary"] = [{
        "text" => summary_text(40),
        "source_refs" => ["stronger-001", "profile-experience-001"]
      }]
      model["skills"] = [{"name" => "Technologies", "items" => [
        {"text" => "Ruby", "source_ref" => "stronger-001"}
      ]}]
      model["alignment"]["requirements"][0]["evidence_refs"] = ["stronger-001"]
      model["quantifier_review"]["used"] = []
      model["projects"] = []
      write_model(path, model)
      stdout, stderr, status = run_tool(
        "validate", "--model", path, "--profile", PROFILE, "--projects", PROJECTS,
        "--ranking", RANKING
      )
      assert status.success?, stderr
      refute_includes JSON.parse(stdout)["warnings"].join(" "), "rank inversion"
    end
  end

  def test_ranking_is_optional
    with_model do |model, path, _directory|
      write_model(path, model)
      stdout, stderr, status = run_tool(
        "validate", "--model", path, "--profile", PROFILE, "--projects", PROJECTS,
        "--ranking", File.join(FIXTURES, "absent-ranking.yaml")
      )
      assert status.success?, stderr
      report = JSON.parse(stdout)
      refute report.dig("checks", "ranking_loaded")
      refute_includes report["warnings"].join(" "), "rank inversion"
    end
  end

  def test_rejects_resume_longer_than_two_pages
    with_model do |model, path, directory|
      bullet = model["experience"][0]["bullets"][0]
      model["experience"][0]["bullets"] = Array.new(4) { bullet.dup }
      model["experience"] = Array.new(20) { model["experience"][0].transform_values { |value| value.is_a?(Array) ? value.map(&:dup) : value } }
      model["layout"]["page_target"] = 2
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["preferences"]["page_target"] = 2
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      write_model(path, model)
      _stdout, stderr, status = run_tool(
        "render", "--model", path, "--profile", profile_path, "--projects", PROJECTS,
        "--policy", POLICY, "--output-dir", File.join(directory, "output")
      )
      refute status.success?
      assert_includes stderr, "two-page maximum"
    end
  end

  # --- Engagements inside a role -------------------------------------------
  #
  # A flat employer block gives every project inside a role the same three or
  # four slots. These cover the nested structure that lets a role carrying many
  # distinct client deliverables show them without inflating the bullet cap.

  def engagement_entry
    {
      "name" => {"text" => "Stronger Client", "source_ref" => "stronger-001"},
      "context" => {"text" => "Ruby, PostgreSQL", "source_ref" => "stronger-001"},
      "bullets" => [
        {"text" => "Implemented a reporting vertical with typed failure handling.",
         "source_ref" => "stronger-001"}
      ]
    }
  end

  def test_engagements_validate_and_render
    with_model do |model, _path, directory|
      model["experience"][0]["engagements"] = [engagement_entry]
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json"), encoding: "UTF-8"))
      assert report["valid"], report["errors"]
    end
  end

  def test_engagement_name_and_bullets_reach_both_documents
    with_model do |model, _path, directory|
      model["experience"][0]["engagements"] = [engagement_entry]
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      runs = docx_runs(File.join(output, "resume.docx"))
      assert_includes runs, "Stronger Client"
      assert_includes runs, "typed failure handling"
    end
  end

  def test_role_bullets_can_render_after_engagements_when_explicitly_requested
    with_model do |model, _path, directory|
      model["experience"][0]["engagements"] = [engagement_entry]
      model["experience"][0]["bullets_position"] = "after_engagements"
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      runs = docx_runs(File.join(output, "resume.docx"))
      assert_operator runs.index("Stronger Client"), :<, runs.index("data import pipeline")
    end
  end

  def test_volunteering_heading_and_details_render_as_real_bullets
    with_model do |model, path, directory|
      profile = YAML.safe_load(File.read(PROFILE), permitted_classes: [Date])
      profile["activities"] = [{
        "id" => "profile-activity-001", "role" => "Technology Instructor",
        "organization" => "Developer Community", "start" => "2020-09",
        "end" => "2021-08", "details" => "Delivered technical training.",
        "kind" => "user-stated"
      }]
      model["layout"]["activities_heading"] = "Volunteering"
      model["activities"] = [{
        "primary" => {"text" => "Technology Instructor", "source_ref" => "profile-activity-001"},
        "secondary" => {"text" => "Developer Community", "source_ref" => "profile-activity-001"},
        "date" => {"text" => "Sep 2020 - Aug 2021", "source_ref" => "profile-activity-001"},
        "details" => [{"text" => "Delivered technical training.", "source_ref" => "profile-activity-001"}]
      }]
      profile_path = File.join(directory, "profile.yaml")
      File.write(profile_path, YAML.dump(profile))
      write_model(path, model)
      output = File.join(directory, "output")
      _stdout, stderr, status = run_tool(
        "render", "--model", path, "--profile", profile_path, "--projects", PROJECTS,
        "--policy", POLICY, "--output-dir", output
      )
      assert status.success?, stderr
      runs = docx_runs(File.join(output, "resume.docx"))
      assert_includes runs, "VOLUNTEERING"
      assert_match(%r{<w:pStyle w:val="ListBullet"/>.*?Delivered technical training\.}m, runs)
    end
  end

  def test_engagement_bullets_are_indented_deeper_than_role_bullets
    with_model do |model, _path, directory|
      model["experience"][0]["engagements"] = [engagement_entry]
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      runs = docx_runs(File.join(output, "resume.docx"))
      policy = JSON.parse(File.read(POLICY, encoding: "UTF-8"))
      role_twips = (policy["bullets"]["text_indent_pt"] * 20).round
      engagement_twips = (policy["bullets"]["engagement_text_indent_pt"] * 20).round
      assert_includes runs, "w:left=\"#{role_twips}\""
      assert_includes runs, "w:left=\"#{engagement_twips}\""
    end
  end

  def test_engagement_under_an_unassociated_employer_is_rejected
    with_model do |model, path, _directory|
      engagement = engagement_entry
      engagement["name"] = {"text" => "Lowest Client", "source_ref" => "lowest-001"}
      engagement["context"] = nil
      engagement["bullets"] = [
        {"text" => "Implemented a CSV export utility with Ruby.", "source_ref" => "lowest-001"}
      ]
      model["experience"][0]["engagements"] = [engagement]
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "preferences.standalone_projects"
    end
  end

  def test_engagement_mixing_two_projects_is_rejected
    with_model do |model, path, _directory|
      engagement = engagement_entry
      engagement["bullets"] << {
        "text" => "Contributed to a data import pipeline supporting 3 formats with Ruby and PostgreSQL.",
        "source_ref" => "fixture-001"
      }
      model["experience"][0]["engagements"] = [engagement]
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "), "mixes sources from multiple projects"
    end
  end

  def test_too_many_role_bullets_beside_engagements_warns
    with_model do |model, _path, directory|
      model["experience"][0]["bullets"] = Array.new(3) do
        {"text" => "Contributed to a data import pipeline supporting 3 formats with Ruby and PostgreSQL.",
         "source_ref" => "fixture-001"}
      end
      model["experience"][0]["engagements"] = [engagement_entry]
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json"), encoding: "UTF-8"))
      assert(
        report["document_validation"]["warnings"].any? { |warning| warning.include?("framing lines is the maximum") },
        report["document_validation"]["warnings"].inspect
      )
    end
  end

  def test_master_resume_allows_four_distinct_role_bullets_beside_engagements
    with_model do |model, _path, directory|
      model["target"] = {
        "mode" => "master", "company" => "General", "role" => "Software Engineer",
        "market" => "europe", "market_basis" => "profile-default",
        "job_country" => nil, "job_country_code" => nil,
        "location_scope" => "unspecified", "location_basis" => "user-request"
      }
      model["basics"]["mobility"] = {
        "text" => "Open to relocation.", "source_ref" => "profile-eligibility-003"
      }
      bullet = model["experience"][0]["bullets"][0]
      model["experience"][0]["bullets"] = Array.new(4) { bullet.dup }
      model["experience"][0]["engagements"] = [engagement_entry]
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      warnings = JSON.parse(
        File.read(File.join(output, "validation.json"), encoding: "UTF-8")
      ).dig("document_validation", "warnings").join(" ")
      refute_includes warnings, "framing lines is the maximum"
      refute_includes warnings, "Historical role 1 has 4 bullets"
    end
  end

  def test_a_role_without_engagements_keeps_the_flat_contract
    with_model do |model, path, _directory|
      refute model["experience"][0].key?("engagements")
      _stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
    end
  end
end
