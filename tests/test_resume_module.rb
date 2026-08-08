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
    raise ArgumentError, "summary needs at least two words per sentence" if word_count < sentences * 2

    words = ["Software", "Engineer"] + Array.new(word_count - 3, "Ruby") + ["PostgreSQL"]
    base, remainder = word_count.divmod(sentences)
    cursor = 0
    Array.new(sentences) do |index|
      size = base + (index < remainder ? 1 : 0)
      sentence = words.slice(cursor, size).join(" ") + "."
      cursor += size
      sentence
    end.join(" ")
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

  def test_requires_two_selected_project_entries
    with_model do |model, path, _directory|
      model["projects"] = model["projects"].first(1)
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "at least 2 Selected Projects entries"
    end
  end

  def test_requires_two_distinct_curated_projects
    with_model do |model, path, _directory|
      model["projects"][1] = {
        "primary" => {"text" => "Second Import View", "source_ref" => "fixture-001"},
        "secondary" => nil,
        "date" => nil,
        "details" => [{
          "text" => "Contributed to a data import pipeline with Ruby.",
          "source_ref" => "fixture-001"
        }]
      }
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "at least two distinct curated projects"
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
      model["target"]["summary_lead"] = "Flutter Mobile Engineer"
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "must begin with target.summary_lead"
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
        "text" => "Worked on the product billing subsystem.",
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
      assert_equal 20.0, report.dig("presentation", "bullet_layout", "text_indent_pt")
      assert_equal 11.0, report.dig("presentation", "bullet_layout", "hanging_pt")
      assert_equal(-1.5, report.dig("presentation", "bullet_layout", "marker_vertical_offset_pt"))
      assert_equal "Casey_Engineer_Software_Engineer_CV",
                   report.dig("presentation", "attachment_stem")
      refute report.dig("document_validation", "pdf_password_protected")
      assert_includes report.dig("document_validation", "warnings").join(" "),
                      "no phone number"
      assert_includes report.dig("document_validation", "warnings").join(" "),
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

  def test_summary_defaults_to_ninety_words_and_four_sentences_in_every_market
    with_model do |model, path, _directory|
      model["summary"][0]["text"] = summary_text(90)
      _stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
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

  def test_summary_rejects_fewer_than_four_sentences
    with_model do |model, path, _directory|
      model["summary"][0]["text"] = summary_text(45, sentences: 3)
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "4 to 6 complete sentences; found 3"
    end
  end

  def test_summary_rejects_more_than_six_sentences
    with_model do |model, path, _directory|
      model["summary"][0]["text"] = summary_text(70, sentences: 7)
      _stdout, stderr, status = validate(model, path)
      refute status.success?
      assert_includes stderr, "4 to 6 complete sentences; found 7"
    end
  end

  def test_renders_selected_projects
    with_model do |model, _path, directory|
      output, _stdout, stderr, status = render_model(model, directory)
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert report["valid"]
      assert_equal 0, report.dig("document_validation", "errors").length
      assert_equal ["stronger", "fixture"], report.dig(
        "source_validation", "project_selection", "named_in_selected_projects"
      )
      validation_text = File.read(File.join(output, "validation.md"))
      assert_includes validation_text, "Project evidence used anywhere: stronger, fixture"
      assert_includes validation_text, "Named in Selected Projects: stronger, fixture"
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

  def test_two_page_resume_uses_only_exact_continuation_contact
    with_model do |model, path, directory|
      bullet = model["experience"][0]["bullets"][0]
      model["experience"][0]["bullets"] = Array.new(4) { bullet.dup }
      model["experience"] = Array.new(8) { model["experience"][0].transform_values { |value| value.is_a?(Array) ? value.map(&:dup) : value } }
      model["layout"]["page_target"] = 2
      write_model(path, model)
      output = File.join(directory, "output")
      _stdout, stderr, status = run_tool(
        "render", "--model", path, "--profile", PROFILE, "--projects", PROJECTS,
        "--policy", POLICY, "--output-dir", output
      )
      assert status.success?, stderr
      report = JSON.parse(File.read(File.join(output, "validation.json")))
      assert_equal 2, report.dig("document_validation", "pdf_pages")
      assert_equal ["Casey Engineer | engineer@example.test"], report.dig("document_validation", "docx_structure", "header_footer_text")
    end
  end

  # --- Enhancement 1: automatic hyperlinks ---------------------------------

  def test_accepts_a_hyperlink_recorded_in_the_profile
    with_model do |model, path, _directory|
      model["experience"][0]["organization"]["url"] = "https://example.test/systems"
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert JSON.parse(stdout)["valid"]
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

  def test_requires_a_confirmed_link_on_every_project_backed_summary_item
    with_model do |model, path, _directory|
      model["summary"][0].delete("url")
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "must carry one of its confirmed project links"
    end
  end

  def test_rejects_a_summary_link_owned_by_a_different_entity
    with_model do |model, path, _directory|
      model["summary"][0]["url"] = "https://example.test/systems"
      stdout, _stderr, status = validate(model, path)
      refute status.success?
      assert_includes JSON.parse(stdout)["errors"].join(" "),
                      "must belong to its source project fixture"
    end
  end

  def test_warns_without_blocking_when_a_summary_project_has_no_confirmed_link
    with_model do |model, path, _directory|
      model["summary"] = [{
        "text" => summary_text(40),
        "source_ref" => "stronger-001"
      }]
      stdout, stderr, status = validate(model, path)
      assert status.success?, stderr
      assert_includes JSON.parse(stdout)["warnings"].join(" "),
                      "summary item backed by stronger has no confirmed project link"
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
      assert_includes pdf, "play.example.test/fixture"
    end
  end

  def test_text_export_prints_addresses_that_are_not_already_visible
    with_model do |model, _path, directory|
      output, _stdout, stderr, status = render_model(model, directory, "--include-text")
      assert status.success?, stderr
      text = File.read(File.join(output, "resume.txt"))
      assert_includes text, "Data Importer (https://play.example.test/fixture)"
      refute_includes text, "engineer@example.test (mailto:"
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
      assert_equal ["stronger", "fixture"], report.dig("project_selection", "selected")
      assert_equal [1, 2], report.dig("project_selection", "ranks")
      assert_equal ["stronger", "fixture"], report.dig("project_selection", "evidence_used")
      assert_equal ["stronger", "fixture"],
                   report.dig("project_selection", "named_in_selected_projects")
    end
  end

  def test_ranking_warns_about_a_rank_inversion
    with_model do |model, path, _directory|
      model["projects"] = [
        {
          "primary" => {"text" => "Data Importer", "source_ref" => "fixture-001"},
          "secondary" => nil,
          "date" => nil,
          "details" => [{
            "text" => "Contributed to a data import pipeline with Ruby.",
            "source_ref" => "fixture-001"
          }]
        },
        {
          "primary" => {"text" => "CSV Export Utility", "source_ref" => "lowest-001"},
          "secondary" => nil,
          "date" => nil,
          "details" => [{
            "text" => "Implemented a CSV export utility with Ruby.",
            "source_ref" => "lowest-001"
          }]
        }
      ]
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
      model["projects"] = [
        {
          "primary" => {"text" => "Data Importer", "source_ref" => "fixture-001"},
          "secondary" => nil,
          "date" => nil,
          "details" => [{
            "text" => "Contributed to a data import pipeline with Ruby.",
            "source_ref" => "fixture-001"
          }]
        },
        {
          "primary" => {"text" => "CSV Export Utility", "source_ref" => "lowest-001"},
          "secondary" => nil,
          "date" => nil,
          "details" => [{
            "text" => "Implemented a CSV export utility with Ruby.",
            "source_ref" => "lowest-001"
          }]
        }
      ]
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
        "source_ref" => "stronger-001"
      }]
      model["skills"] = [{"name" => "Technologies", "items" => [
        {"text" => "Ruby", "source_ref" => "stronger-001"}
      ]}]
      model["alignment"]["requirements"][0]["evidence_refs"] = ["stronger-001"]
      model["quantifier_review"]["used"] = []
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
      write_model(path, model)
      _stdout, stderr, status = run_tool(
        "render", "--model", path, "--profile", PROFILE, "--projects", PROJECTS,
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
        report["document_validation"]["warnings"].any? { |warning| warning.include?("framing lines is the target") },
        report["document_validation"]["warnings"].inspect
      )
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
