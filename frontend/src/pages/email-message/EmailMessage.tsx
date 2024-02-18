import React, { useEffect, useState } from "react";
import {
    Badge, Card, Flex, Heading, View, Button, Text, Divider
} from "@aws-amplify/ui-react";
import { useNavigate, useParams } from "react-router-dom";
import { get, del } from 'aws-amplify/api';
import PostalMime from 'postal-mime';

const EmailMessages = () => {
    const [message, setMessage] = useState<any>(null)
    const [summary, setSummary] = useState<string>(null)
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<unknown>(null);
    const params = useParams();
    const emailAddress = params.addressId;
    const messageId = params.messageId;
    const navigate = useNavigate();
    const handleBackClick = (emailAddress) => {
        navigate(`/email-accounts/${encodeURIComponent(emailAddress)}`);
    };

    async function getMessage(emailAddress, messageId) {
        try {
            setLoading(true)
            const restOperation = get({
                apiName: 'disposible',
                path: `addresses/${emailAddress}/${messageId}`,
            });
            const { body } = await restOperation.response;
            const raw = await body.json();
            const parser = new PostalMime()
            const response = await parser.parse(raw["body"]);
            setMessage(response);
            setSummary(raw["summary"])
        } catch (err) {
            console.error('GET call failed: ', err);
            setError(err);
        } finally {
            setLoading(false)
        }
    }

    async function handleDeleteMessage(emailAddress, messageId) {
        try {
            setLoading(true)
            const restOperation = del({
                apiName: 'disposible',
                path: `addresses/${emailAddress}/${messageId}`,
            });
            await restOperation.response;
            handleBackClick(emailAddress)
            console.log('DELETE call succeeded');
        } catch (err) {
            console.error('DELETE call failed: ', err);
            setError(err);
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        getMessage(emailAddress, messageId); // Call the function to fetch addresses
    }, []);

    if (loading) return <div>Loading...</div>;
    if (error) return <div>Error fetching message</div>;
    if (!message) return <div>No message data</div>;

    return (
        <>
            <Flex className="header-flex">
                <div className="email-header">
                    <h2>Email Message: {messageId}</h2>
                </div>
            </Flex>
            <Flex justifyContent="flex-start" alignItems="center">
                <Button size="small" isLoading={loading} isDisabled={loading} onClick={() => handleDeleteMessage(emailAddress, messageId)} variation="destructive">Delete</Button>
                <div style={{ flex: 1 }}></div> {/* Spacer element */}
                <Button size="small" isLoading={loading} isDisabled={loading} onClick={() => handleBackClick(emailAddress)}>Back</Button>
            </Flex>
            <br></br>
            <br />
            {summary && (
                <Card style={{
                    width: '100%', // Set width to 100% to fit the screen
                    maxWidth: '100%', // Ensure it doesn't exceed the screen width
                    marginBottom: '1rem',
                    boxSizing: 'border-box', // This ensures padding is included in the width calculation
                }}>
                    <Text textDecoration="underline">Summary</Text>
                    <br></br>
                    <Text>{summary}</Text>
                </Card>
            )}
            <br></br>
            <View
                backgroundColor="var(--amplify-colors-white)"
                borderRadius="6px"
                maxWidth="100%"
                padding="1rem"
                minHeight="80vh"
            >
                <Card>
                    <Flex
                        direction="column"
                        alignItems="flex-start">
                        <Badge size="small" variation="info">
                            From: {message.from.address}
                        </Badge>
                        <Badge size="small" variation="success">
                            To: {message.to[0].address}
                        </Badge>
                        <Heading level={5}>
                            Subject: {message.subject}
                        </Heading>
                        <Divider />
                        <div className="email-content" dangerouslySetInnerHTML={{ __html: message.html }} />
                    </Flex>
                </Card>
            </View>
        </>
    );
};

export default EmailMessages;