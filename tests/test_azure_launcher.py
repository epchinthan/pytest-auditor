"""Azure launcher orchestration with fake cloud commands; no Azure resources created."""
import json
import os
import subprocess
from pathlib import Path

import pytest

LAUNCHER = Path(__file__).resolve().parents[1] / 'runazure.sh'


@pytest.fixture
def azure_commands(tmp_path):
    commands = tmp_path / 'bin'
    commands.mkdir()
    log = tmp_path / 'commands.jsonl'
    az = commands / 'az'
    az.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
log = pathlib.Path(os.environ['FAKE_AZ_LOG'])
with log.open('a') as output:
    output.write(json.dumps(['az', *args]) + '\\n')
logged_in = log.with_suffix('.login')
if args[:2] == ['account', 'show'] and os.environ.get('FAKE_LOGIN_ABSENT') == '1' and not logged_in.exists():
    sys.exit(1)
if args[:1] == ['login']:
    logged_in.touch()
if args[:2] == ['account', 'get-access-token'] and os.environ.get('FAKE_TOKEN_EXPIRED') == '1' and not logged_in.exists():
    sys.exit(1)
if args[:2] == ['account', 'list']:
    scenario = os.environ.get('FAKE_SUBSCRIPTIONS', 'single')
    if scenario == 'single':
        print('sub-one\\tExample subscription\\tFalse')
    elif scenario == 'multiple-default':
        print('sub-one\\tFirst subscription\\tFalse')
        print('sub-two\\tDefault subscription\\tTrue')
    elif scenario == 'multiple-no-default':
        print('sub-one\\tFirst subscription\\tFalse')
        print('sub-two\\tSecond subscription\\tFalse')
if args[:2] == ['account', 'show'] and '--query' in args:
    print('Example subscription')
if args[:2] == ['group', 'show']:
    print(os.environ.get('FAKE_EXISTING_LOCATION', 'westeurope'))
if args[:2] == ['webapp', 'deploy']:
    from zipfile import ZipFile
    source = pathlib.Path(args[args.index('--src-path') + 1])
    with ZipFile(source) as archive:
        files = sorted(archive.namelist())
    log.with_suffix('.context').write_text(json.dumps({'path': str(source), 'files': files}))
    if os.environ.get('FAKE_DEPLOY_FAIL') == '1':
        print(os.environ.get('FAKE_BUILD_ERROR', 'Build failed'), file=sys.stderr)
        sys.exit(1)
if os.environ.get('FAKE_RESOURCES_MISSING') == '1' and '--query' not in args and (
    args[:2] in [['acr', 'show'], ['webapp', 'show']] or args[:3] == ['appservice', 'plan', 'show']
):
    sys.exit(1)
if (args[:2] == ['acr', 'create'] or args[:3] == ['appservice', 'plan', 'create']) and os.environ.get('FAKE_REGION_ERROR'):
    if args[args.index('--location') + 1] == 'westeurope':
        print(os.environ['FAKE_REGION_ERROR'], file=sys.stderr)
        sys.exit(1)
if args[:2] == ['provider', 'show']:
    print('Registered')
if args[:3] == ['appservice', 'plan', 'show'] and '--query' in args:
    print(os.environ.get('FAKE_PLAN_SKU', 'B1'))
if args[:2] == ['acr', 'show'] and '--query' in args:
    print('registry.azurecr.io' if args[args.index('--query') + 1] == 'loginServer' else '/subscriptions/sub-one/registries/registry')
if args[:3] == ['webapp', 'identity', 'assign']:
    print('identity-id')
if args[:3] == ['role', 'assignment', 'list']:
    print('0')
if args[:2] == ['webapp', 'show'] and '--query' in args:
    print('pytest-auditor.example.azurewebsites.net')
''')
    az.chmod(0o755)
    for name in ['curl', 'xdg-open', 'docker']:
        tool = commands / name
        tool.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
with pathlib.Path(os.environ['FAKE_AZ_LOG']).open('a') as output:
    output.write(json.dumps([pathlib.Path(sys.argv[0]).name, *sys.argv[1:]]) + '\\n')
if pathlib.Path(sys.argv[0]).name == 'docker' and sys.argv[1:] == ['info'] and os.environ.get('FAKE_DOCKER_UNAVAILABLE') == '1':
    sys.exit(1)
if pathlib.Path(sys.argv[0]).name == 'curl':
    print('<form id="audit-form">')
''')
        tool.chmod(0o755)
    env = {**os.environ, 'PATH': str(commands) + os.pathsep + os.environ['PATH'],
           'FAKE_AZ_LOG': str(log)}
    # Do not let developer-machine settings change these simulated deployments.
    for key in list(env):
        if key.startswith('AZURE_'):
            env.pop(key)
    return env, log


def run_launcher(env, tmp_path):
    return subprocess.run([str(LAUNCHER)], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=20)


# Assert actual arguments and uploaded files, not just a printed success message.
def test_source_deployment_runtime_startup_and_https(azure_commands, tmp_path):
    env, log = azure_commands
    result = run_launcher(env, tmp_path)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    deploy = next(call for call in calls if call[:3] == ['az', 'webapp', 'deploy'])
    assert deploy[deploy.index('--type') + 1] == 'zip'
    config = next(call for call in calls if call[:4] == ['az', 'webapp', 'config', 'set'])
    assert config[config.index('--linux-fx-version') + 1] == 'PYTHON|3.12'
    assert config[config.index('--startup-file') + 1] == 'python web_server.py --host 0.0.0.0 --port 8000'
    settings = next(call for call in calls if call[:5] == ['az', 'webapp', 'config', 'appsettings', 'set'])
    assert 'SCM_DO_BUILD_DURING_DEPLOYMENT=true' in settings
    assert calls.index(settings) < calls.index(deploy)
    assert not any(call[0] == 'docker' or 'acr' in call or 'AcrPull' in call for call in calls)
    assert ['xdg-open', 'https://pytest-auditor.example.azurewebsites.net'] in calls
    context = json.loads(log.with_suffix('.context').read_text())
    assert 'web/index.html' in context['files']
    assert 'requirements.txt' in context['files']
    assert not any(path.startswith(('tests/', '.git/', '.azure-cli/', '.aws/', '.venv/'))
                   or '__pycache__' in path or path.endswith('.pyc') for path in context['files'])
    assert 'Dockerfile' not in context['files']
    assert not Path(context['path']).exists()


# Unattended mode must never fall back to an interactive authentication prompt.
def test_unattended_run_requires_existing_login(azure_commands, tmp_path):
    env, log = azure_commands
    result = run_launcher({**env, 'FAKE_LOGIN_ABSENT': '1', 'AZURE_NONINTERACTIVE': '1'}, tmp_path)
    assert result.returncode != 0
    assert 'No Azure login found' in result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert not any(call[:2] == ['az', 'login'] for call in calls)
    assert not any(call[:3] == ['az', 'webapp', 'deploy'] for call in calls)


@pytest.mark.parametrize('managed', [False, True], ids=['initial-login', 'managed-identity'])
def test_missing_login_uses_selected_authentication(azure_commands, tmp_path, managed):
    env, log = azure_commands
    settings = {'FAKE_LOGIN_ABSENT': '1', 'AZURE_OPEN_BROWSER': '0'}
    if managed:
        settings['AZURE_MANAGED_IDENTITY'] = '1'
    result = run_launcher({**env, **settings}, tmp_path)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    login = next(call for call in calls if call[:2] == ['az', 'login'])
    assert ('--identity' in login) == managed
    assert not any(call[0] == 'xdg-open' for call in calls)


# Failure should clean uploaded staging files without opening an application URL.
def test_failed_deployment_cleans_build_context(azure_commands, tmp_path):
    env, log = azure_commands
    result = run_launcher({**env, 'FAKE_DEPLOY_FAIL': '1'}, tmp_path)
    assert result.returncode != 0
    context = json.loads(log.with_suffix('.context').read_text())
    assert not Path(context['path']).exists()
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert not any(call[0] == 'xdg-open' for call in calls)


# Login discovers available subscriptions; no user-supplied IDs are required.
@pytest.mark.parametrize('scenario,expected_id', [
    ('single', 'sub-one'), ('multiple-default', 'sub-two'),
])
def test_subscription_is_discovered_after_login(azure_commands, tmp_path, scenario, expected_id):
    env, log = azure_commands
    result = run_launcher({**env, 'FAKE_LOGIN_ABSENT': '1', 'FAKE_SUBSCRIPTIONS': scenario}, tmp_path)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert ['az', 'account', 'set', '--subscription', expected_id] in calls
    assert calls.index(next(call for call in calls if call[:2] == ['az', 'login'])) < calls.index(
        next(call for call in calls if call[:3] == ['az', 'account', 'list'])
    )


def test_expired_token_triggers_browser_login(azure_commands, tmp_path):
    env, log = azure_commands
    result = run_launcher({**env, 'FAKE_TOKEN_EXPIRED': '1'}, tmp_path)
    assert result.returncode == 0, result.stderr
    assert 'Opening Azure sign-in in your browser' in result.stdout
    assert any(json.loads(line)[:2] == ['az', 'login'] for line in log.read_text().splitlines())


@pytest.mark.parametrize('scenario,message', [
    ('none', 'no enabled Azure subscription'),
    ('multiple-no-default', 'Multiple subscriptions'),
])
def test_subscription_problems_stop_before_resource_creation(azure_commands, tmp_path, scenario, message):
    env, log = azure_commands
    result = run_launcher({**env, 'FAKE_SUBSCRIPTIONS': scenario, 'AZURE_NONINTERACTIVE': '1'}, tmp_path)
    assert result.returncode != 0
    assert message in result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert not any(call[:3] == ['az', 'provider', 'register'] for call in calls)
    assert not any(call[:3] == ['az', 'webapp', 'deploy'] for call in calls)


def test_existing_resource_group_region_is_discovered(azure_commands, tmp_path):
    env, log = azure_commands
    result = run_launcher({**env, 'FAKE_EXISTING_LOCATION': 'northeurope'}, tmp_path)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    deployment = next(call for call in calls if call[:3] == ['az', 'group', 'create'])
    assert deployment[deployment.index('--location') + 1] == 'northeurope'


# The pip-installed az wrapper can require a global 'python' that does not exist.
# A local CLI must instead use its own interpreter, including when az is on PATH.
@pytest.mark.parametrize('local_on_path', [False, True], ids=['local-install', 'local-on-path'])
def test_local_azure_cli_uses_venv_interpreter(azure_commands, tmp_path, local_on_path):
    import shutil
    import sys

    env, log = azure_commands
    project = tmp_path / 'project'
    project.mkdir()
    shutil.copy2(LAUNCHER, project / 'runazure.sh')
    for name in ['Dockerfile', 'requirements.txt', '__main__.py', '__init__.py',
                 'web_server.py', 'web_sources.py', '.dockerignore']:
        (project / name).write_text('')
    for name in ['core', 'scanning', 'reporting', 'web']:
        (project / name).mkdir()
    commands = Path(env['PATH'].split(os.pathsep)[0])
    driver = commands / 'azure-driver'
    (commands / 'az').rename(driver)
    local_bin = project / '.azure-cli' / 'bin'
    local_bin.mkdir(parents=True)
    wrapper = local_bin / 'az'
    wrapper.write_text('#!/bin/sh\nexit 99\n')
    wrapper.chmod(0o755)
    interpreter = local_bin / 'python'
    interpreter.write_text(f'''#!{sys.executable}
import os, sys
if sys.argv[1] == '-c':
    sys.exit(0)
assert sys.argv[1:3] == ['-m', 'azure.cli']
if sys.argv[3:] == ['--version']:
    sys.exit(0)
os.execv({str(driver)!r}, [{str(driver)!r}, *sys.argv[3:]])
''')
    interpreter.chmod(0o755)
    if local_on_path:
        env['PATH'] = str(local_bin) + os.pathsep + env['PATH']
    result = subprocess.run([str(project / 'runazure.sh')], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'Application URL:' in result.stdout


# First deployment creates dedicated resources; reruns reuse them without a second plan.
@pytest.mark.parametrize('missing', [True, False], ids=['first-deployment', 'rerun'])
def test_app_service_resource_creation_and_reuse(azure_commands, tmp_path, missing):
    env, log = azure_commands
    result = run_launcher({**env, 'FAKE_RESOURCES_MISSING': '1' if missing else '0'}, tmp_path)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert any(call[:4] == ['az', 'appservice', 'plan', 'create'] for call in calls) == missing
    assert any(call[:3] == ['az', 'webapp', 'create'] for call in calls) == missing
    if missing:
        plan = next(call for call in calls if call[:4] == ['az', 'appservice', 'plan', 'create'])
        assert '--is-linux' in plan
        assert plan[plan.index('--sku') + 1] == 'B1'
    assert not any('AcrPull' in call for call in calls)
    assert not any('Microsoft.App' in call or 'containerapp' in call for call in calls)



@pytest.mark.parametrize('missing', [True, False], ids=['create-free-plan', 'reuse-free-plan'])
def test_free_plan_disables_always_on(azure_commands, tmp_path, missing):
    # Free hosting must work on first deployment and when reusing a free plan
    # without repeating the SKU override on subsequent invocations.
    env, log = azure_commands
    settings = {**env, 'FAKE_PLAN_SKU': 'F1',
                'FAKE_RESOURCES_MISSING': '1' if missing else '0'}
    if missing:
        settings['AZURE_APP_SERVICE_SKU'] = 'F1'
    result = run_launcher(settings, tmp_path)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    config = next(call for call in calls if call[:4] == ['az', 'webapp', 'config', 'set'])
    assert config[config.index('--always-on') + 1] == 'false'
    if missing:
        plan = next(call for call in calls if call[:4] == ['az', 'appservice', 'plan', 'create'])
        assert plan[plan.index('--sku') + 1] == 'F1'


@pytest.mark.parametrize('error', ['RequestDisallowedByAzure https://aka.ms/locationineligible',
                                  'Operation cannot be completed without additional quota'])
def test_ineligible_region_retries_nearby_region(azure_commands, tmp_path, error):
    env, log = azure_commands
    result = run_launcher({**env, 'FAKE_RESOURCES_MISSING': '1',
                           'FAKE_REGION_ERROR': error}, tmp_path)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    creates = [call for call in calls if call[:4] == ['az', 'appservice', 'plan', 'create']]
    assert [call[call.index('--location') + 1] for call in creates] == ['westeurope', 'northeurope']
    assert creates[-1][creates[-1].index('--location') + 1] == 'northeurope'


@pytest.mark.parametrize('settings', [
    {'AZURE_LOCATION': 'westeurope', 'FAKE_REGION_ERROR': 'https://aka.ms/locationineligible'},
    {'FAKE_REGION_ERROR': 'AuthorizationFailed: access denied'},
], ids=['explicit-region-is-respected', 'permission-error-is-not-retried'])
def test_region_fallback_preserves_settings_and_other_errors(azure_commands, tmp_path, settings):
    env, log = azure_commands
    result = run_launcher({**env, 'FAKE_RESOURCES_MISSING': '1', **settings}, tmp_path)
    assert result.returncode != 0
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert len([call for call in calls if call[:4] == ['az', 'appservice', 'plan', 'create']]) == 1
    assert not any(call[:3] == ['az', 'webapp', 'deploy'] for call in calls)



