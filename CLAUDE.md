# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

The repository holds math explanation-video storyboards built with the "讲题视频 Pro" skill
(repo `xulipeficec49-cpu/explain-video-pro`, which owns the renderer, assets and scripts — none of it is vendored here).

- `videos/<题目>/make_sb.py` generates that problem's storyboard JSON (`<题目>.json`); edit the script, not the JSON.
- Build outputs (`build_*/`, frames, audio) are git-ignored.

## Commands

Run from any directory, with the skill checked out (e.g. at `../explain-video-pro`):

```
python videos/huanxing-zhuiji/make_sb.py                                   # regenerate the storyboard
python <skill>/scripts/make_video.py videos/huanxing-zhuiji/环形跑道.json check            # gate: 0 ERROR
python <skill>/scripts/make_video.py videos/huanxing-zhuiji/环形跑道.json preview --fake   # layout frames
python <skill>/scripts/make_video.py videos/huanxing-zhuiji/环形跑道.json render --fake    # silent mp4
python <skill>/scripts/make_video.py videos/huanxing-zhuiji/环形跑道.json tts              # voiceover (needs OPENROUTER_API_KEY + DASHSCOPE_API_KEY)
python <skill>/scripts/make_video.py videos/huanxing-zhuiji/环形跑道.json render           # final mp4 with voice
```

On Linux, `preview` loads the sheet font from the relative path `C:/Windows/Fonts/arial.ttf`; run it from a
directory where that path exists (a symlink to any TTF works).

## Git workflow

- The default branch is `main`.
- Development for AI-assisted changes happens on dedicated feature branches (e.g. `claude/...`); do not commit directly to `main`.
- Push feature branches with `git push -u origin <branch-name>`.
