"""Steerable village-moment scenarios (see app.py's interactive_moments
feature) -- each is a two-penguin situation with two distinct, differently
worded resolutions, not a generic Agree/Disagree. option_a is always the
cooperative/friendly resolution -- the ONLY one that calls
increment_relationship() for real (see app.py:_apply_moment_resolution()).
option_b is always the confrontational one -- like an unresolved/timed-out
moment, it never touches the relationship.

{a}/{b} placeholders are filled in with the two penguins' display names at
moment-creation time (see app.py's _create_moment()), pre-wrapped in
highlight_name() the same way generate_action_text() already does for
AUTONOMOUS_ACTIONS templates, so flavor_text/outcome text can be dropped
straight into event_log/the popup without further processing."""

MOMENT_SCENARIOS = [
    {
        "situation": '{a} and {b} are fighting over a leftover fish at the Sea Lion Pit.',
        "option_a": {
            "label": 'They should share',
            "outcome": 'They split the fish and eat it together happily.',
        },
        "option_b": {
            "label": 'Let them fight',
            "outcome": "{a} wrestles the fish out of {b}'s flippers.",
        },
    },
    {
        "situation": '{a} and {b} both grabbed the last clean bench in the village square.',
        "option_a": {
            "label": 'Scoot over',
            "outcome": 'They squeeze onto the bench together, a little cramped but fine.',
        },
        "option_b": {
            "label": 'Stare them down',
            "outcome": '{b} gives up and stands, muttering under their breath.',
        },
    },
    {
        "situation": '{a} accused {b} of eating the herbs {a} was drying on the windowsill.',
        "option_a": {
            "label": 'Talk it out',
            "outcome": 'Turns out it was a seagull. They laugh it off.',
        },
        "option_b": {
            "label": 'Hold the grudge',
            "outcome": '{a} refuses to speak to {b} for the rest of the day.',
        },
    },
    {
        "situation": "{a} and {b} are arguing over who gets the last stool at Club Soda's bar.",
        "option_a": {
            "label": 'Flip for it',
            "outcome": '{a} wins the coin flip, {b} takes it in stride.',
        },
        "option_b": {
            "label": 'Shove past',
            "outcome": '{b} shoulders past {a} and claims the stool anyway.',
        },
    },
    {
        "situation": "{a} left their hat at {b}'s igloo and {b} started wearing it.",
        "option_a": {
            "label": 'Let them keep it',
            "outcome": '{a} decides it looks better on {b} anyway.',
        },
        "option_b": {
            "label": 'Demand it back',
            "outcome": "{a} snatches the hat off {b}'s head mid-sentence.",
        },
    },
    {
        "situation": '{a} and {b} both want to pray at the same spot in the Cursed Temple.',
        "option_a": {
            "label": 'Take turns',
            "outcome": 'They alternate five-minute shifts, very civilized.',
        },
        "option_b": {
            "label": 'Refuse to move',
            "outcome": "{a} plants their flippers and won't budge.",
        },
    },
    {
        "situation": '{a} thinks {b} copied their fashion sense at the Boutique.',
        "option_a": {
            "label": 'Call it a compliment',
            "outcome": '{a} decides imitation is flattering, actually.',
        },
        "option_b": {
            "label": 'Start a rivalry',
            "outcome": 'They now dress in deliberately clashing outfits.',
        },
    },
    {
        "situation": '{a} and {b} disagree over who found the shiny rock first.',
        "option_a": {
            "label": 'Split the credit',
            "outcome": 'They agree to co-discover it, engraving both names.',
        },
        "option_b": {
            "label": 'Claim sole ownership',
            "outcome": '{a} pockets the rock and walks off.',
        },
    },
    {
        "situation": '{b} keeps humming loudly while {a} is trying to nap on the village bench.',
        "option_a": {
            "label": 'Hum along',
            "outcome": '{a} gives up on napping and joins the tune instead.',
        },
        "option_b": {
            "label": 'Snap awake and complain',
            "outcome": '{a} storms off to nap somewhere quieter.',
        },
    },
    {
        "situation": '{a} and {b} both showed up to Parkmusement wanting the same performance slot.',
        "option_a": {
            "label": 'Do a duet',
            "outcome": 'They combine acts into an unexpectedly great show.',
        },
        "option_b": {
            "label": 'Compete for it',
            "outcome": '{a} shoves in first and hogs the whole slot.',
        },
    },
    {
        "situation": '{a} borrowed gold from {b} and "forgot" to pay it back.',
        "option_a": {
            "label": 'Forgive the debt',
            "outcome": "{b} shrugs it off — what's a little gold between friends.",
        },
        "option_b": {
            "label": 'Demand repayment',
            "outcome": '{b} follows {a} around the village until they pay.',
        },
    },
    {
        "situation": '{a} and {b} are arguing over whose snowman is better.',
        "option_a": {
            "label": 'Declare a tie',
            "outcome": 'They shake flippers and agree both are masterpieces.',
        },
        "option_b": {
            "label": 'Knock the other one down',
            "outcome": '{a} "accidentally" bumps into {b}\'s snowman.',
        },
    },
    {
        "situation": "{b} keeps leaving their fishing gear at {a}'s favorite spot by the pond.",
        "option_a": {
            "label": 'Share the spot',
            "outcome": 'They fish side by side and actually enjoy the company.',
        },
        "option_b": {
            "label": 'Move the gear',
            "outcome": "{a} tosses {b}'s rod into the snow out of spite.",
        },
    },
    {
        "situation": '{a} is convinced {b} is spreading rumors about them at the Bank.',
        "option_a": {
            "label": 'Clear the air',
            "outcome": 'It was a misunderstanding; they laugh about it after.',
        },
        "option_b": {
            "label": 'Spread a counter-rumor',
            "outcome": '{a} starts a rumor of their own about {b}.',
        },
    },
    {
        "situation": '{a} and {b} both want the last spot in line at the Boutique mirror.',
        "option_a": {
            "label": 'Let them go first',
            "outcome": '{a} steps aside, {b} thanks them warmly.',
        },
        "option_b": {
            "label": 'Cut the line',
            "outcome": "{b} slips past {a} while they're not looking.",
        },
    },
    {
        "situation": '{a} thinks {b} is hogging all the good ice blocks near the Barracks.',
        "option_a": {
            "label": 'Divide the pile',
            "outcome": 'They split the ice blocks evenly, no hard feelings.',
        },
        "option_b": {
            "label": 'Race for the rest',
            "outcome": '{a} grabs an armful before {b} can react.',
        },
    },
    {
        "situation": "{b} keeps interrupting {a}'s karaoke set at Club Soda.",
        "option_a": {
            "label": 'Duet it out',
            "outcome": 'They end up harmonizing surprisingly well.',
        },
        "option_b": {
            "label": 'Grab the mic back',
            "outcome": '{a} yanks the microphone away mid-song.',
        },
    },
    {
        "situation": '{a} and {b} both claim they saw the four-leaf clover first.',
        "option_a": {
            "label": 'Press it together',
            "outcome": 'They agree to keep it in a shared scrapbook.',
        },
        "option_b": {
            "label": 'Snatch it away',
            "outcome": '{b} grabs the clover before {a} can react.',
        },
    },
    {
        "situation": "{a} is upset {b} didn't invite them to their book club (attendance: 1).",
        "option_a": {
            "label": 'Extend an invite',
            "outcome": '{b} welcomes {a}, and attendance doubles to 2.',
        },
        "option_b": {
            "label": 'Start a rival club',
            "outcome": '{a} opens a competing book club out of spite.',
        },
    },
    {
        "situation": '{a} and {b} disagree over whether the Penguin Bank is actually haunted.',
        "option_a": {
            "label": 'Investigate together',
            "outcome": 'They explore it side by side, equally spooked.',
        },
        "option_b": {
            "label": 'Dare the other to go alone',
            "outcome": '{a} pushes {b} toward the door and bolts.',
        },
    },
    {
        "situation": '{b} "accidentally" knocked over {a}\'s sandcastle-style igloo model.',
        "option_a": {
            "label": 'Rebuild it together',
            "outcome": 'They rebuild it even better than before.',
        },
        "option_b": {
            "label": 'Storm off angry',
            "outcome": "{a} refuses {b}'s help and rebuilds alone, fuming.",
        },
    },
    {
        "situation": '{a} and {b} both want the last spell fragment on the Temple altar.',
        "option_a": {
            "label": 'Split the fragment',
            "outcome": 'They agree to share its power evenly.',
        },
        "option_b": {
            "label": 'Grab it first',
            "outcome": '{b} snatches it before {a} can reach the altar.',
        },
    },
    {
        "situation": '{a} thinks {b} is flirting with their crush at the frozen pond.',
        "option_a": {
            "label": 'Talk it through',
            "outcome": 'Turns out {b} was just being friendly. Crisis averted.',
        },
        "option_b": {
            "label": 'Confront them publicly',
            "outcome": '{a} makes a scene in front of the whole pond.',
        },
    },
    {
        "situation": '{a} and {b} disagree over who should pay the Club Soda tab.',
        "option_a": {
            "label": 'Split the bill',
            "outcome": 'They divide it evenly and toast to fairness.',
        },
        "option_b": {
            "label": 'Dine and dash',
            "outcome": '{a} bolts, leaving {b} to cover the whole tab.',
        },
    },
    {
        "situation": '{b} keeps "borrowing" {a}\'s gear from the Barracks rack without asking.',
        "option_a": {
            "label": 'Set up a sharing system',
            "outcome": "They start a rotation everyone's happy with.",
        },
        "option_b": {
            "label": 'Lock it up',
            "outcome": "{a} starts hiding their gear where {b} can't find it.",
        },
    },
    {
        "situation": '{a} and {b} both want credit for organizing the village snowball fight.',
        "option_a": {
            "label": 'Share the spotlight',
            "outcome": "They're announced as co-organizers together.",
        },
        "option_b": {
            "label": 'Take all the credit',
            "outcome": '{a} tells everyone it was entirely their idea.',
        },
    },
    {
        "situation": "{a} is annoyed {b} keeps napping on the Award Hall's trophy display bench.",
        "option_a": {
            "label": 'Let them nap there too',
            "outcome": '{a} joins the nap; the bench fits two, barely.',
        },
        "option_b": {
            "label": 'Wake them up rudely',
            "outcome": "{a} bangs a trophy loudly right next to {b}'s ear.",
        },
    },
    {
        "situation": "{a} and {b} disagree over who's the better dancer.",
        "option_a": {
            "label": 'Dance together',
            "outcome": 'They turn it into a duet everyone applauds.',
        },
        "option_b": {
            "label": 'Dance-off showdown',
            "outcome": '{a} tries to outshine {b} and knocks over a snowman.',
        },
    },
    {
        "situation": '{b} keeps "reviewing" {a}\'s cooking a little too harshly.',
        "option_a": {
            "label": 'Ask for real feedback',
            "outcome": '{a} takes the critique to heart and improves.',
        },
        "option_b": {
            "label": 'Ban them from the kitchen',
            "outcome": '{a} refuses to let {b} near the pot again.',
        },
    },
    {
        "situation": '{a} and {b} both want the last room at the Penguin Hotel.',
        "option_a": {
            "label": 'Share the room',
            "outcome": 'They split it and end up becoming closer friends.',
        },
        "option_b": {
            "label": 'Bribe the front desk',
            "outcome": '{a} slips the clerk gold to lock {b} out.',
        },
    },
    {
        "situation": "{a} thinks {b}'s lucky streak at the Bank is somehow rigged.",
        "option_a": {
            "label": 'Ask them to teach it',
            "outcome": '{b} shares their "secret," which is just luck.',
        },
        "option_b": {
            "label": 'Accuse them publicly',
            "outcome": '{a} demands an audit in front of everyone.',
        },
    },
    {
        "situation": "{b} keeps setting off tiny fireworks near {a}'s igloo at odd hours.",
        "option_a": {
            "label": 'Set up a schedule',
            "outcome": 'They agree on a fireworks curfew everyone likes.',
        },
        "option_b": {
            "label": 'Douse the fuse',
            "outcome": "{a} storms out and stomps out {b}'s fireworks.",
        },
    },
    {
        "situation": '{a} and {b} disagree over who gets to name the new village cat.',
        "option_a": {
            "label": 'Combine the names',
            "outcome": 'The cat ends up with a ridiculous double name.',
        },
        "option_b": {
            "label": "Veto the other's pick",
            "outcome": "{a} secretly renames the cat behind {b}'s back.",
        },
    },
    {
        "situation": '{a} is upset {b} keeps beating their high score at the Boutique dress-up game.',
        "option_a": {
            "label": 'Ask for tips',
            "outcome": '{b} teaches {a} a few tricks, scores rise together.',
        },
        "option_b": {
            "label": 'Sabotage the leaderboard',
            "outcome": "{a} tries to erase {b}'s score entry.",
        },
    },
    {
        "situation": '{b} keeps "borrowing" {a}\'s umbrella during the village\'s fake weather events.',
        "option_a": {
            "label": 'Take turns with it',
            "outcome": 'They huddle under it together, staying dry.',
        },
        "option_b": {
            "label": 'Snatch it back mid-storm',
            "outcome": '{a} yanks the umbrella away, leaving {b} soaked.',
        },
    },
    {
        "situation": '{a} and {b} both claim the last cheese wheel at the tasting stall.',
        "option_a": {
            "label": 'Split the wheel',
            "outcome": 'They cut it evenly and swap tasting notes.',
        },
        "option_b": {
            "label": 'Grab and run',
            "outcome": '{b} grabs the whole wheel and bolts.',
        },
    },
    {
        "situation": '{a} thinks {b} is hogging the best fishing rock at the Sea Lion Pit.',
        "option_a": {
            "label": 'Rotate spots',
            "outcome": 'They agree to swap rocks every hour.',
        },
        "option_b": {
            "label": 'Push for the spot',
            "outcome": "{a} nudges {b} off the rock when no one's looking.",
        },
    },
    {
        "situation": "{b} keeps interrupting {a}'s meditation at the Cursed Temple with loud humming.",
        "option_a": {
            "label": 'Meditate to the hum',
            "outcome": "{a} decides it's oddly soothing after all.",
        },
        "option_b": {
            "label": 'Storm off to meditate elsewhere',
            "outcome": '{a} relocates, visibly annoyed.',
        },
    },
    {
        "situation": '{a} and {b} disagree over whose penguin chick drawing is more accurate.',
        "option_a": {
            "label": 'Frame both',
            "outcome": 'They hang both drawings side by side at the Boutique.',
        },
        "option_b": {
            "label": "Rip the other's down",
            "outcome": "{a} tears {b}'s drawing off the wall.",
        },
    },
    {
        "situation": '{a} is convinced {b} used a rigged dice at their Board Games duel.',
        "option_a": {
            "label": 'Reroll fairly',
            "outcome": 'They agree to a fresh, fair rematch.',
        },
        "option_b": {
            "label": 'Flip the board',
            "outcome": '{a} knocks the whole board off the table.',
        },
    },
    {
        "situation": '{b} keeps "testing" {a}\'s perfume samples without asking, at the Boutique.',
        "option_a": {
            "label": 'Offer a proper sample',
            "outcome": '{a} hands {b} their own bottle to try.',
        },
        "option_b": {
            "label": 'Hide the perfume',
            "outcome": '{a} starts locking their samples away.',
        },
    },
    {
        "situation": '{a} and {b} both want the last warm spot by the Club Soda fireplace.',
        "option_a": {
            "label": 'Squeeze in together',
            "outcome": 'They share the warmth and swap village gossip.',
        },
        "option_b": {
            "label": 'Elbow for the spot',
            "outcome": '{b} wedges {a} out and claims it solo.',
        },
    },
    {
        "situation": '{a} thinks {b} is copying their signature ice-sculpting style.',
        "option_a": {
            "label": 'Collaborate on a piece',
            "outcome": 'They co-sculpt something better than either alone.',
        },
        "option_b": {
            "label": 'Sabotage the sculpture',
            "outcome": '{a} "accidentally" knocks over {b}\'s ice art.',
        },
    },
    {
        "situation": '{b} keeps hogging the tea ceremony kettle at the village gathering.',
        "option_a": {
            "label": 'Brew a second pot',
            "outcome": 'They end up sharing tea and swapping stories.',
        },
        "option_b": {
            "label": 'Snatch the kettle',
            "outcome": '{a} grabs it mid-pour, spilling tea everywhere.',
        },
    },
    {
        "situation": '{a} and {b} disagree over who gets to ring the doorbell melody they both wrote.',
        "option_a": {
            "label": 'Merge the melodies',
            "outcome": 'They compose a joint tune everyone loves.',
        },
        "option_b": {
            "label": 'Overwrite the tune',
            "outcome": "{a} deletes {b}'s version and keeps their own.",
        },
    },
    {
        "situation": '{a} is annoyed {b} keeps "borrowing" gold from the shared donation jar.',
        "option_a": {
            "label": 'Set a fair limit together',
            "outcome": 'They agree on borrowing rules everyone respects.',
        },
        "option_b": {
            "label": 'Lock the jar',
            "outcome": "{a} starts hiding the jar somewhere {b} can't find it.",
        },
    },
    {
        "situation": '{b} keeps trying to hypnotize {a} "just to see if it works."',
        "option_a": {
            "label": 'Let them try, for fun',
            "outcome": "{a} plays along; it doesn't work, they laugh about it.",
        },
        "option_b": {
            "label": 'Refuse and walk off',
            "outcome": '{a} storms away, annoyed at being used as a test subject.',
        },
    },
    {
        "situation": '{a} and {b} both claim they spotted the cryptid near the frozen pond first.',
        "option_a": {
            "label": 'Co-author the sighting report',
            "outcome": 'They submit a joint account to the village log.',
        },
        "option_b": {
            "label": 'Discredit the other',
            "outcome": '{a} tells everyone {b}\'s sighting was "just a rock."',
        },
    },
    {
        "situation": '{a} thinks {b} is hogging the Award Hall leaderboard bragging rights.',
        "option_a": {
            "label": 'Celebrate both records',
            "outcome": 'They agree to split the spotlight on the plaque.',
        },
        "option_b": {
            "label": 'Demand a rematch',
            "outcome": '{a} challenges {b} right there, tempers flaring.',
        },
    },
    {
        "situation": '{b} keeps "juggling" {a}\'s prized ice blocks without permission.',
        "option_a": {
            "label": 'Turn it into a show',
            "outcome": 'They juggle together for a delighted crowd.',
        },
        "option_b": {
            "label": 'Confiscate the ice blocks',
            "outcome": '{a} snatches them mid-air, ending the act.',
        },
    },
]
