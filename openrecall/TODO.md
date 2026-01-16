- [ ] make a simple executable file to install
Just use pyinstaller on Windows. I don't know how to cross-package it to Linux and MacOS on my Windows machine.
No plan to package models now, but I think it may be a future feature.

- [ ] make a pyproject.toml for packaging
Now we need Pillow==10.3.0, actually its latest version is 11.3.0.
Setup error on python 3.13.5, maybe that's why origin repo need Python<3.13.
```
Collecting Pillow==10.3.0 (from OpenRecall==0.8)
  Downloading https://mirrors.tuna.tsinghua.edu.cn/pypi/web/packages/ef/43/c50c17c5f7d438e836c169e343695534c38c77f60e7c90389bd77981bc21/pillow-10.3.0.tar.gz (46.6 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 46.6/46.6 MB 61.5 MB/s eta 0:00:00
  Installing build dependencies ... done
  Getting requirements to build wheel ... error
  error: subprocess-exited-with-error

  × Getting requirements to build wheel did not run successfully.
  │ exit code: 1
  ╰─> [21 lines of output]
      Traceback (most recent call last):
        File "%USERPROFILE%\miniconda3\envs\test\Lib\site-packages\pip\_vendor\pyproject_hooks\_in_process\_in_process.py", line 389, in <module>
          main()
          ~~~~^^
        File "%USERPROFILE%\miniconda3\envs\test\Lib\site-packages\pip\_vendor\pyproject_hooks\_in_process\_in_process.py", line 373, in main
          json_out["return_val"] = hook(**hook_input["kwargs"])
                                   ~~~~^^^^^^^^^^^^^^^^^^^^^^^^
        File "%USERPROFILE%\miniconda3\envs\test\Lib\site-packages\pip\_vendor\pyproject_hooks\_in_process\_in_process.py", line 143, in get_requires_for_build_wheel
          return hook(config_settings)
        File "%USERPROFILE%\AppData\Local\Temp\pip-build-env-yjaj5rvu\overlay\Lib\site-packages\setuptools\build_meta.py", line 331, in get_requires_for_build_wheel
          return self._get_build_requires(config_settings, requirements=[])
                 ~~~~~~~~~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        File "%USERPROFILE%\AppData\Local\Temp\pip-build-env-yjaj5rvu\overlay\Lib\site-packages\setuptools\build_meta.py", line 301, in _get_build_requires
          self.run_setup()
          ~~~~~~~~~~~~~~^^
        File "%USERPROFILE%\AppData\Local\Temp\pip-build-env-yjaj5rvu\overlay\Lib\site-packages\setuptools\build_meta.py", line 317, in run_setup
          exec(code, locals())
          ~~~~^^^^^^^^^^^^^^^^
        File "<string>", line 33, in <module>
        File "<string>", line 27, in get_version
      KeyError: '__version__'
      [end of output]

  note: This error originates from a subprocess, and is likely not a problem with pip.
error: subprocess-exited-with-error

× Getting requirements to build wheel did not run successfully.
│ exit code: 1
╰─> See above for output.

note: This error originates from a subprocess, and is likely not a problem with pip.
```

- [ ] make it more accurate
Change to better models?

- [ ] run on GPU if needed
SentenceTransformer in nlp.py can have an argument `device` saying:
```
Device (like "cuda", "cpu", "mps", "npu") that should be used for computation. If None, checks if a GPU can be used.
```
Why does it not choose GPU automatically on my machine?