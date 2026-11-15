from app import seed as seed_module

DEFAULT_PASSWORDS = (
    "Admin@2026",
    "Engineer@2026",
    "Manager@2026",
    "Viewer@2026",
    "GroupAdmin@2026",
)


def test_production_seed_summary_omits_all_credentials(capsys):
    seed_module.print_seed_summary(print_credentials=False)
    output = capsys.readouterr()
    combined = output.out + output.err
    assert "Seed data created successfully!" in combined
    for password in DEFAULT_PASSWORDS:
        assert password not in combined


def test_development_seed_summary_keeps_existing_hint(capsys):
    seed_module.print_seed_summary(print_credentials=True)
    output = capsys.readouterr().out
    assert "admin/Admin@2026" in output


def test_parse_args_no_print_credentials():
    args = seed_module.parse_args(["--no-print-credentials"])
    assert args.no_print_credentials is True


def test_parse_args_defaults_to_print_credentials():
    args = seed_module.parse_args([])
    assert args.no_print_credentials is False
