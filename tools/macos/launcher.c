// Econoclast.app/Contents/MacOS/Econoclast: run `econoclast app` on the Python inside the bundle.
//
// The bundle carries its own relocatable CPython under Contents/Resources/python. This launcher
// embeds that interpreter (libpython) instead of exec'ing it, so the window process stays the
// app's own executable: LaunchServices, the Dock (including a kept-in-Dock tile) and the menu bar
// all see Econoclast.app. sys.executable still names the real interpreter, so the detached hunts,
// the arsenal MCP server and the Fabrica start ordinary Python processes.
//
// It also gives Python a PATH where the agents live (claude, codex, npx, uv), keeps the user's
// site-packages out, never writes bytecode into the signed bundle, and logs to ~/.econoclast/app.log.
#include <Python.h>

#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

static void setup_env(const char *home) {
  const char *inherited = getenv("PATH");
  if (!inherited || !*inherited) inherited = "/usr/bin:/bin:/usr/sbin:/sbin";
  const char *fmt = "%s/.local/bin:%s/.claude/local:%s/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:%s";
  size_t n = strlen(fmt) + 3 * strlen(home) + strlen(inherited) + 1;
  char *path = malloc(n);
  if (path) {
    snprintf(path, n, fmt, home, home, home, inherited);
    setenv("PATH", path, 1);
    free(path);
  }
  setenv("PYTHONNOUSERSITE", "1", 1);  // inherited by the hunts and the arsenal
  setenv("PYTHONDONTWRITEBYTECODE", "1", 1);
  setenv("ECONOCLAST_BUNDLE", "1", 1);
  unsetenv("PYTHONHOME");
  unsetenv("PYTHONPATH");
  unsetenv("PYTHONSTARTUP");
  unsetenv("VIRTUAL_ENV");
}

static void redirect_log(const char *home) {
  // Finder starts apps with output on /dev/null; keep a log instead. A terminal keeps its tty.
  if (isatty(STDERR_FILENO)) return;
  char dir[PATH_MAX], log[PATH_MAX];
  snprintf(dir, sizeof dir, "%s/.econoclast", home);
  mkdir(dir, 0755);
  snprintf(log, sizeof log, "%s/app.log", dir);
  int fd = open(log, O_WRONLY | O_CREAT | O_APPEND, 0644);
  if (fd < 0) return;
  dup2(fd, STDOUT_FILENO);
  dup2(fd, STDERR_FILENO);
  close(fd);
}

static int fail(PyConfig *config, PyStatus status) {
  PyConfig_Clear(config);
  if (PyStatus_IsExit(status)) return status.exitcode;
  Py_ExitStatusException(status);  // prints the reason and exits
}

int main(int argc, char **argv) {
  char exe[PATH_MAX], real[PATH_MAX], pyhome[PATH_MAX], py[PATH_MAX];
  uint32_t size = sizeof exe;
  if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, real)) {
    fprintf(stderr, "Econoclast: cannot locate the app bundle\n");
    return 1;
  }
  char *contents = dirname(dirname(real));  // .../Econoclast.app/Contents
  snprintf(pyhome, sizeof pyhome, "%s/Resources/python", contents);
  snprintf(py, sizeof py, "%s/bin/python3.12", pyhome);

  const char *home = getenv("HOME");
  if (!home || !*home) home = "/tmp";
  setup_env(home);
  redirect_log(home);

  PyConfig config;
  PyConfig_InitPythonConfig(&config);
  config.parse_argv = 1;
  config.user_site_directory = 0;
  config.write_bytecode = 0;
  config.safe_path = 1;  // never import from the working directory
  PyStatus status = PyConfig_SetBytesString(&config, &config.home, pyhome);
  if (PyStatus_Exception(status)) return fail(&config, status);
  status = PyConfig_SetBytesString(&config, &config.executable, py);
  if (PyStatus_Exception(status)) return fail(&config, status);
  status = PyConfig_SetBytesString(&config, &config.program_name, py);
  if (PyStatus_Exception(status)) return fail(&config, status);

  char **args = calloc((size_t)argc + 5, sizeof(char *));
  if (!args) return 1;
  int k = 0;
  args[k++] = py;
  args[k++] = "-m";
  args[k++] = "econoclast";
  args[k++] = "app";
  for (int i = 1; i < argc; i++)
    if (strncmp(argv[i], "-psn_", 5) != 0) args[k++] = argv[i];  // old Finder process serial numbers
  status = PyConfig_SetBytesArgv(&config, k, args);
  if (PyStatus_Exception(status)) return fail(&config, status);

  status = Py_InitializeFromConfig(&config);
  if (PyStatus_Exception(status)) return fail(&config, status);
  PyConfig_Clear(&config);
  return Py_RunMain();
}
