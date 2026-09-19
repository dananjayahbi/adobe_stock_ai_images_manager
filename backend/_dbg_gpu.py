from services.upscale import gpus
cli = gpus.find_cli()
for args in [
    ("-i","__e__.jpg","-o","__e__.png","-m","__e__","-n","__e__","-z","2","-g","-1","-f","png","-v"),
    ("-i","__e__.jpg","-o","__e__.png","-m","__e__","-n","__e__","-z","2","-g","99","-f","png","-v"),
]:
    import subprocess
    c = subprocess.run([cli, *args], capture_output=True, text=True, timeout=20)
    print("ARGS g=", args[args.index("-g")+1], "LEN:", len(c.stdout)+len(c.stderr))
    print(repr((c.stdout+c.stderr)[:300]))
    print("---")
