# Fictional fixture setup only. Production editors must review each clause.
module ResumeTestSupport
  def freeze_fixture(root, application, status: "proceed")
    id = application.fetch("id")
    applications = File.join(root, "applications")
    FileUtils.mkdir_p(applications)
    File.write(File.join(applications, "#{id}.yaml"), YAML.dump(application))
    return if application.dig("targeting", "resume_mode") == "master"

    digest, err, result = Open3.capture3(
      "python3", File.expand_path("../scripts/ekb_screening.py", __dir__),
      id, "--root", root
    )
    raise err unless result.success?
    File.write(File.join(applications, "#{id}.screening.yaml"), YAML.dump({
      "id" => id, "kind" => "screening",
      "decision" => {"status" => status, "decided_at" => "2026-07-21", "posting_sha256" => digest.strip}
    }))
  end
end
