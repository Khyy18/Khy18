"""Тесты для deploy-скриптов и конфигурации."""

import subprocess

import yaml


def test_deploy_sh_valid_bash():
    """Проверяет, что deploy.sh является валидным bash-скриптом."""
    result = subprocess.run(
        ["bash", "-n", "deploy/deploy.sh"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"deploy.sh syntax error: {result.stderr}"


def test_rollback_sh_valid_bash():
    """Проверяет, что rollback.sh является валидным bash-скриптом."""
    result = subprocess.run(
        ["bash", "-n", "deploy/rollback.sh"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"rollback.sh syntax error: {result.stderr}"


def test_docker_compose_prod_valid_yaml():
    """Проверяет, что docker-compose.prod.yml - валидный YAML."""
    with open("deploy/docker-compose.prod.yml") as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "services" in data


def test_docker_compose_prod_has_expected_services():
    """Проверяет наличие всех ожидаемых сервисов."""
    with open("deploy/docker-compose.prod.yml") as f:
        data = yaml.safe_load(f)
    services = data["services"]
    assert "zenith-blue" in services
    assert "zenith-green" in services
    assert "nginx" in services
    assert "redis" in services


def test_nginx_conf_contains_upstream_blocks():
    """Проверяет, что nginx.conf содержит upstream-блоки."""
    with open("deploy/nginx.conf") as f:
        content = f.read()
    assert "upstream blue" in content
    assert "upstream green" in content
    assert "8081" in content
    assert "8082" in content
    assert "proxy_pass" in content


def test_active_upstream_conf_default():
    """Проверяет, что active_upstream.conf по умолчанию указывает на blue."""
    with open("deploy/active_upstream.conf") as f:
        content = f.read()
    assert "8081" in content
    assert "upstream active" in content
