# agent-kit profile options: keys, allowed values and defaults.
# Shared by configure.sh (terminal) and config_ui.py (web form), which parses
# the OPT_* lines below, so keep the simple KEY='value' format.
# Compatible with bash 3.2.

# Profile (preferences; can be synced through a private repository)
OPT_PROFILE_KEYS='UI_LANG CONTENT_LANG REPLY_LANG DOCS_LANG WORK_MODE DESIGN PLANNING COMMITS SCAFFOLD STACKS SKILLS TOOLS'
# Machine (this computer only)
OPT_MACHINE_KEYS='PROJECT_DIRS'

PROFILE_FORMAT_VERSION='1'
MACHINE_FORMAT_VERSION='1'

# Choice lists. "*" in a list means free text is also accepted.
OPT_UI_LANG_CHOICES='en zh-CN'
OPT_CONTENT_LANG_CHOICES='en zh-CN'
OPT_REPLY_LANG_CHOICES='en zh-CN zh-TW ja ko es fr de *'
OPT_DOCS_LANG_CHOICES='reply en zh-CN zh-TW ja ko es fr de *'
OPT_WORK_MODE_CHOICES='solo team'
OPT_DESIGN_CHOICES='none some'
OPT_PLANNING_CHOICES='full light off'
OPT_COMMITS_CHOICES='conventional free'
OPT_TOOLS_CHOICES='claude codex'
# STACKS and SKILLS choices come from the repository (stacks/*, skills/*).

# Defaults. UI_LANG and REPLY_LANG default to the system language (see common.sh).
OPT_CONTENT_LANG_DEFAULT='en'
OPT_DOCS_LANG_DEFAULT='reply'
OPT_WORK_MODE_DEFAULT='solo'
OPT_DESIGN_DEFAULT='none'
OPT_PLANNING_DEFAULT='full'
OPT_COMMITS_DEFAULT='conventional'
OPT_SCAFFOLD_DEFAULT=''
OPT_SKILLS_DEFAULT='all'
OPT_TOOLS_DEFAULT='claude codex'
# OPT_STACKS_DEFAULT: every stack in the repository.
