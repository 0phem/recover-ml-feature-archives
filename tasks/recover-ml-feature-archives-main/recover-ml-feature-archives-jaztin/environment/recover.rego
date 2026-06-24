package churnshield.recover

import future.keywords.if
import future.keywords.in

default allow := false

recoverable contains shard.path if {
    some shard in input.shards
    shard.row_count >= input.min_rows
    shard.has_required_columns == true
    shard.checksum_verified == true
}

deny contains msg if {
    count(recoverable) == 0
    msg := "No recoverable shards found: all shards failed row-count, column, or checksum checks."
}

deny contains msg if {
    some shard in input.shards
    shard.checksum_verified == false
    not shard.path in recoverable
    msg := sprintf("Shard %v is unverified or has a bad checksum and will be excluded.", [shard.path])
}
