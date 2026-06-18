from safecode.enterprise import __about__


def test_enterprise_about_importable():
    assert isinstance(__about__.__version__, str)
    assert __about__.__version__
