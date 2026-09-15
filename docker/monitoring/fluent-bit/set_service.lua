function set_service(tag, timestamp, record)
    if record["service"] == nil then
        record["service"] = tag
    end
    if record["container_id"] ~= nil then
        record["stream"] = record["source"] or "stdout"
    else
        record["stream"] = "file"
    end
    return 1, timestamp, record
end