-- Shield.app: pick what to open on the NVIDIA Shield, then run it in Terminal.
-- Uses the `shield` command installed at ~/.local/bin/shield.

set shieldCmd to (POSIX path of (path to home folder)) & ".local/bin/shield"

set choices to {¬
	"Claude Code session (Telegram bot)", ¬
	"Debian shell", ¬
	"Termux shell", ¬
	"Status", ¬
	"Start Claude", ¬
	"Stop Claude"}
set commandFor to {"claude", "debian", "termux", "status", "start", "stop"}

set picked to choose from list choices with title "NVIDIA Shield" with prompt "Open on the Shield:" default items {item 1 of choices} OK button name "Open" cancel button name "Cancel"
if picked is false then return

set pickedName to item 1 of picked
repeat with i from 1 to count of choices
	if item i of choices is pickedName then set subcommand to item i of commandFor
end repeat

if subcommand is "stop" then
	display dialog "Stop the Claude session on the Shield? The Telegram bot goes offline until you start it again." buttons {"Cancel", "Stop"} default button "Cancel" cancel button "Cancel" with icon caution
end if

tell application "Terminal"
	activate
	do script quoted form of shieldCmd & " " & subcommand
end tell
